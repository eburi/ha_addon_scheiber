import can
import time
import threading
import sys
import termios
import tty
import os
import sys
import select
import termios
import tty
import atexit

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
            print(f"|{' ' * 11}|{' ' * 11}|{' ' * 5} {mask}")

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
# Main loop
# ------------------------------------------

def main():
    global key_pressed, binary_mode, stats_mode

    set_raw_terminal()

    print("Opening CAN interface can0...")
    bus = can.interface.Bus(channel="can0", interface="socketcan")

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
            if msg:
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