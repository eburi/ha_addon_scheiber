import can # type: ignore
import time
import sys
import termios
import tty
import select
import termios
import tty
import atexit
import argparse

# ------------------------------------------
# GLOBAL STATE
# ------------------------------------------

key_pressed = None
binary_mode = False       # toggled by 'b'
stats_mode = False        # toggled by 's'

# per CAN ID:
# entry = {
#   "last_data": bytes,
#   "last_time": float,
#   "delta_ms": float,
#   "count": int,
#   "first_seen": float
# }
can_table = {}


# ------------------------------------------
# Keyboard listener (nonblocking)
# ------------------------------------------

# Save original terminal settings
orig_termios = termios.tcgetattr(sys.stdin)

def restore_terminal():
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, orig_termios)

# Ensure terminal is restored no matter what
atexit.register(restore_terminal)

def set_raw_terminal():
    tty.setcbreak(sys.stdin.fileno())

def read_key_nonblocking():
    """Returns one character if available, otherwise None."""
    dr, dw, de = select.select([sys.stdin], [], [], 0)
    if dr:
        return sys.stdin.read(1)
    return None

# ------------------------------------------
# Formatting helpers
# ------------------------------------------

def fmt_hex(data):
    return " ".join(f"{b:02X}" for b in data)

def fmt_bin(data):
    return " ".join(f"{b:08b}" for b in data)

def diff_mask(prev, curr, binary):
    out = []

    if binary:
        for (a, b) in zip(prev, curr):
            ab = f"{a:08b}"
            bb = f"{b:08b}"
            out.append("".join("^" if x != y else " " for x, y in zip(ab, bb)))
        return " ".join(out)
    else:
        for (a, b) in zip(prev, curr):
            out.append("^^" if a != b else "  ")
        return " ".join(out)


# ------------------------------------------
# Display modes
# ------------------------------------------

def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def show_histogram_view():
    """Draw a cansniffer-like screen of all CAN IDs."""
    global can_table, binary_mode

    clear_screen()
    print("|  Δt(ms) |   CAN ID  | Len | Data")
    print("-" * 80)

    for cid, entry in sorted(can_table.items()):
        delta = entry["delta_ms"]
        data = entry["last_data"]
        length = len(data)

        if binary_mode:
            data_str = fmt_bin(data)
        else:
            data_str = fmt_hex(data)

        print(f"| {delta:7.1f} | {cid:08X} | {length:3d} | {data_str}")

        # diff mask only if we have older data
        if entry.get("prev_data") is not None:
            mask = diff_mask(entry["prev_data"], data, binary_mode)
            print(f"|{' ' * 9}|{' ' * 10}|{' ' * 5}| {mask}")

    print("\nPress 'b' for HEX/BIN, 's' for stats, Ctrl+C to quit.")


def show_stats_view():
    """Display basic message statistics."""
    clear_screen()
    print("========= STATISTICS =========\n")

    now = time.time()
    for cid, entry in sorted(can_table.items()):
        count = entry["count"]
        first = entry["first_seen"]
        freq = count / (now - first) if now > first else 0

        print(f"ID {cid:08X}")
        print(f"  Messages: {count}")
        print(f"  First seen: {time.strftime('%H:%M:%S', time.localtime(first))}")
        print(f"  Last seen:  {time.strftime('%H:%M:%S', time.localtime(entry['last_time']))}")
        print(f"  Frequency:  {freq:.2f} msg/sec\n")

    print("Press 's' to return to histogram view.")


# ------------------------------------------
# CAN message processing
# ------------------------------------------
def match_inverted_filters(msg, filter_list):
    for f in filter_list:
        if f["inverted"]:
            if (msg.arbitration_id & f["can_mask"]) == (f["can_id"] & f["can_mask"]):
                return False  # reject this one
    return True

def update_can_entry(msg):
    """Update stored stats + diff tracking for a CAN message."""
    global can_table

    cid = msg.arbitration_id
    now = time.time()

    if cid not in can_table:
        can_table[cid] = {
            "last_data": msg.data,
            "prev_data": None,
            "last_time": now,
            "delta_ms": 0.0,
            "count": 1,
            "first_seen": now,
        }
    else:
        entry = can_table[cid]
        entry["prev_data"] = entry["last_data"]
        entry["last_data"] = msg.data
        entry["delta_ms"] = (now - entry["last_time"]) * 1000.0
        entry["last_time"] = now
        entry["count"] += 1

# ------------------------------------------
# Argument Handling
# ------------------------------------------
def parse_canutils_filter(fstr):
    """
    Parse a can-utils format filter like '123:7FF' or '1ABCDE:1FFFFFFF'
    Returns a dict for python-can.
    """
    fstr = fstr.strip()

    # Inverted mask form: ID~MASK (rarely used)
    inverted = False
    if "~" in fstr:
        cid, mask = fstr.split("~", 1)
        inverted = True
    else:
        cid, mask = fstr.split(":", 1)

    can_id = int(cid, 16)
    can_mask = int(mask, 16)

    # Determine if extended frame
    extended = can_id > 0x7FF or can_mask > 0x7FF

    return {
        "can_id": can_id,
        "can_mask": can_mask,
        "extended": extended,
        "inverted": inverted
    }

# ------------------------------------------
# Main loop
# ------------------------------------------

def main():
    global key_pressed, binary_mode, stats_mode

    set_raw_terminal()

    parser = argparse.ArgumentParser(description="CAN sniffer tool")
    parser.add_argument(
        "-i", "--interface",
        default="can0",
        help="CAN interface to use (default: can0)"
    )
    parser.add_argument(
        "-f", "--filter",
        action="append",
        help="CAN filter in can-utils format: <id>:<mask> (multiple allowed)"
    )
    args = parser.parse_args()

    interface = args.interface
    print(f"Opening CAN interface {interface}...")

    filters = []
    if args.filter:
        for f in args.filter:
            info = parse_canutils_filter(f)
            if info["inverted"]:
                print(f"WARNING: Inverted filter '{f}' not supported at driver-level; applying software filter.")
            else:
                filters.append({
                    "can_id": info["can_id"],
                    "can_mask": info["can_mask"],
                    "extended": info["extended"]
                })
    bus = can.interface.Bus(
        channel=interface,
        interface="socketcan",
        can_filters=filters if len(filters) > 0 else None
    )

    last_refresh = 0
    try:
        while True:

            # Handle key events
            key = read_key_nonblocking()
            if key == "b":
                binary_mode = not binary_mode
            elif key == "s":
                stats_mode = not stats_mode

            # Read CAN
            msg = bus.recv(timeout=0.05)
            if msg and match_inverted_filters(msg, filters):
                update_can_entry(msg)

            # Refresh display ~10 times per second
            now = time.time()
            if now - last_refresh > 0.10:
                last_refresh = now

                if stats_mode:
                    show_stats_view()
                else:
                    show_histogram_view()

    except KeyboardInterrupt:
        print("\nExiting…")
        bus.shutdown()

    finally:    
        restore_terminal()
        bus.shutdown()


if __name__ == "__main__":
    main()