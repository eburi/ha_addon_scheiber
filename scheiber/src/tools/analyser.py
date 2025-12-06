import argparse
import atexit
import pprint
import select
import sys
import termios
import time
import tty

import can  # type: ignore

# ------------------------------------------
# GLOBAL STATE
# ------------------------------------------

key_pressed = None
binary_mode = False  # toggled by 'b'
stats_mode = False  # toggled by 's'
dump_mode = False  # toggled by 'd'
change_only_mode = True  # toggled by 'c'
canid_name_map = {}
name_col_width = 0
filters = []
inverted_filters = []

record_mode = False  # toggled by 'r'
MAX_HISTORY = 10  # last 10 messages per sender

# per CAN ID:
# entry = {
#   "last_data": bytes,
#   "last_time": float,
#   "delta_ms": float,
#   "count": int,
#   "first_seen": float
# }
can_table = {}

# ANSI colors
CLR_RESET = "\033[0m"
CLR_GREEN = "\033[92m"
CLR_YELLOW = "\033[93m"

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


def fmt_hex(data, prev=None):
    """HEX output, colorized if prev provided."""
    out = []
    for i, b in enumerate(data):
        if prev is not None and i < len(prev) and b != prev[i]:
            out.append(f"{CLR_GREEN}{b:02X}{CLR_RESET}")
        else:
            out.append(f"{b:02X}")
    return " ".join(out)


def fmt_bin(data, prev=None):
    """Binary output, colorized if prev provided."""
    out = []
    for i, b in enumerate(data):
        curr_bits = f"{b:08b}"
        if prev is not None and i < len(prev) and b != prev[i]:
            prev_bits = f"{prev[i]:08b}"
            bitwise_colored = [
                f"{CLR_GREEN if prev_bit != curr_bit else ''}{curr_bit}{CLR_RESET if prev_bit != curr_bit else ''}"
                for (prev_bit, curr_bit) in zip(prev_bits, curr_bits)
            ]
            out.append("".join(bitwise_colored))
        else:
            out.append(curr_bits)
    return " ".join(out)


def diff_mask(prev, curr, binary):
    if prev is None:
        return ""

    if binary:
        mask_parts = []
        for a, b in zip(prev, curr):
            if a != b:
                bits_prev = f"{a:08b}"
                bits_current = f"{b:08b}"
                mask_parts.append(f"{CLR_YELLOW}")
                for prev_bit, curr_bit in zip(bits_prev, bits_current):
                    mask_parts.append("^" if prev_bit != curr_bit else " ")
                mask_parts.append(f"{CLR_RESET}")
                mask_parts.append(" ")  # Spacer
            else:
                mask_parts.append("         ")
        return "".join(mask_parts).rstrip()

    else:
        mask_parts = []
        for a, b in zip(prev, curr):
            if a != b:
                mask_parts.append(f"{CLR_YELLOW}^^ {CLR_RESET}")
            else:
                mask_parts.append("   ")
        return "".join(mask_parts).rstrip()


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
    if name_col_width > 0:
        print(f"|  Δt(ms) |  CAN ID  | {'Name':<{name_col_width}} | Len | Data")
    else:
        print("|  Δt(ms) |  CAN ID  | Len | Data")
    print("-" * 80)

    for cid, entry in sorted(can_table.items()):
        delta = entry["delta_ms"]
        data = entry["last_data"]
        length = len(data)

        if binary_mode:
            data_str = fmt_bin(data, prev=entry.get("prev_data"))
        else:
            data_str = fmt_hex(data, prev=entry.get("prev_data"))

        name = canid_name_map.get(cid, "")
        if name_col_width > 0:
            print(
                f"| {delta:7.1f} | {cid:08X} | {name:<{name_col_width}} | {length:3d} | {data_str}"
            )
        else:
            print(f"| {delta:7.1f} | {cid:08X} | {length:3d} | {data_str}")

        # diff mask only if we have older data
        mask = ""
        if entry.get("prev_data") is not None:
            mask = diff_mask(entry["prev_data"], data, binary_mode)
        if name_col_width > 0:
            # prefix: time column + ID + name + len column + separator
            prefix = f"|{' ' * 9}|{' ' * 10}| {' ' * name_col_width} |{' ' * 5}| "
        else:
            prefix = f"|{' ' * 9}|{' ' * 10}|{' ' * 5}| "

        print(prefix + mask)

        show_history_block(cid, entry)

    print("\nPress 'b' for HEX/BIN, 's' for stats, Ctrl+C to quit.")


def show_history_block(cid, entry):
    """Print the last 10 messages under the ID entry."""
    if not record_mode:
        return

    history = entry.get("history", [])
    if not history:
        return

    for h in history:
        if binary_mode:
            data_str = fmt_bin(h["data"])
        else:
            data_str = fmt_hex(h["data"])

        ts = time.strftime("%H:%M:%S", time.localtime(h["timestamp"]))

        print(f"|         |          |                {ts} | {data_str}")


def show_stats_view():
    global filters, inverted_filters

    """Display basic message statistics."""
    clear_screen()
    print("========= STATISTICS =========\n")

    now = time.time()
    for cid, entry in sorted(can_table.items()):
        count = entry["count"]
        first = entry["first_seen"]
        freq = count / (now - first) if now > first else 0

        print(
            f"ID {cid:08X}: Messages: {count:5d} Frequency:  {freq:.2f}msg/sec First seen: {time.strftime('%H:%M:%S', time.localtime(first))} Last seen:  {time.strftime('%H:%M:%S', time.localtime(entry['last_time']))}"
        )

    hex_pp = HexPrettyPrinter()

    print("\nFilters used for canbus-init:\n")
    hex_pp.pprint(filters)

    print("\nInverted Filters used for canbus-init:\n")
    hex_pp.pprint(inverted_filters)

    print("Press 's' to return to histogram view.")


def dump_message(msg):
    """Print a single CAN frame in dump mode."""
    entry = can_table.get(msg.arbitration_id)
    if not entry:
        return

    curr = entry.get("last_data")
    last_displayed = entry.get("last_displayed_data")

    # Determine if this message is different from the last one we displayed
    changed = (last_displayed is None) or (last_displayed != curr)

    # In change-only mode: skip unchanged messages
    if change_only_mode:
        if changed:
            dump_message_print(msg, entry, binary_mode=False)
            dump_message_print(msg, entry, binary_mode=True)
            # Update last displayed data
            entry["last_displayed_data"] = bytes(curr)
    else:
        dump_message_print(msg, entry, binary_mode)


def dump_message_print(msg, entry, binary_mode=False):
    """Print a single CAN frame in dump mode."""

    ts = time.localtime(entry["last_time"])
    ms = int((entry["last_time"] % 1) * 1000)
    timestamp = time.strftime("%H:%M:%S", ts) + f".{ms:03d}"

    prev = entry.get("prev_data")
    data = entry["last_data"]

    if binary_mode:
        data_str = fmt_bin(data, prev=prev)
    else:
        data_str = fmt_hex(data, prev=prev)

    name = canid_name_map.get(msg.arbitration_id, "")
    diff = diff_mask(prev, data, binary_mode)

    if name_col_width > 0:
        print(
            f"{timestamp} {msg.arbitration_id:08X} {name:<{name_col_width}} {data_str}"
        )
    else:
        print(f"{timestamp} {msg.arbitration_id:08X} {data_str}")

    if diff:
        print(
            f"{' ' * len(timestamp)} {' ' * 8}{' ' * (name_col_width + 1) if name_col_width > 0 else ''} {diff}"
        )


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
            "history": [],
            "last_displayed_data": None,  # Track last data we actually printed in dump mode
        }
    else:
        entry = can_table[cid]
        # Only update prev_data if the message content actually changed
        if entry["last_data"] != msg.data:
            entry["prev_data"] = entry["last_data"]
        entry["last_data"] = msg.data
        entry["delta_ms"] = (now - entry["last_time"]) * 1000.0
        entry["last_time"] = now
        entry["count"] += 1

        entry["history"].append({"timestamp": now, "data": msg.data, "dlc": msg.dlc})

        # Keep only last MAX_HISTORY
        if len(entry["history"]) > MAX_HISTORY:
            entry["history"].pop(0)


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
        "inverted": inverted,
    }


def load_canid_map(path):
    """
    Load CANID→Name mappings from a CSV file with format:
    CANID;Name;
    """
    mapping = {}
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split(";")
                if len(parts) < 2:
                    continue

                cid_str = parts[0].strip()
                name = parts[1].strip()

                # Remove optional 0x
                if cid_str.lower().startswith("0x"):
                    cid_str = cid_str[2:]

                try:
                    cid = int(cid_str, 16)
                except ValueError:
                    continue

                mapping[cid] = name

    except FileNotFoundError:
        print(f"ERROR: CANID map file '{path}' not found.")

    return mapping


class HexPrettyPrinter(pprint.PrettyPrinter):
    def format(self, object, context, maxlevels, level):
        if isinstance(object, int):
            # Convert integer to hex string and return it with a flag indicating
            # it's a string, not a structure that needs further formatting.
            return hex(object), True, False
        else:
            # For other types, defer to the base class's format method.
            return pprint.PrettyPrinter.format(self, object, context, maxlevels, level)


# ------------------------------------------
# Main loop
# ------------------------------------------


def main():
    global key_pressed
    global binary_mode
    global stats_mode
    global canid_name_map
    global name_col_width
    global filters
    global inverted_filters
    global record_mode
    global dump_mode
    global change_only_mode

    set_raw_terminal()

    parser = argparse.ArgumentParser(description="CAN sniffer tool")
    parser.add_argument(
        "-i", "--interface", default="can1", help="CAN interface to use (default: can0)"
    )
    parser.add_argument(
        "-f",
        "--filter",
        action="append",
        help="CAN filter in can-utils format: <id>:<mask> (multiple allowed)",
    )
    parser.add_argument(
        "--canid-map",
        help="Path to CSV file mapping CAN IDs to device names (format: CANID;Name;)",
    )
    args = parser.parse_args()

    interface = args.interface
    print(f"Opening CAN interface {interface}...")

    filters = []
    inverted_filters = []
    if args.filter:
        for f in args.filter:
            info = parse_canutils_filter(f)
            if info["inverted"]:
                print(
                    f"WARNING: Inverted filter '{f}' not supported at driver-level; applying software filter."
                )
                inverted_filters.append(info)
            else:
                filters.append(
                    {
                        "can_id": info["can_id"],
                        "can_mask": info["can_mask"],
                        "extended": info["extended"],
                    }
                )
    bus = can.interface.Bus(
        channel=interface,
        interface="socketcan",
        can_filters=filters if len(filters) > 0 else None,
    )

    if args.canid_map:
        canid_name_map = load_canid_map(args.canid_map)
        print(f"Loaded {len(canid_name_map)} CAN ID mappings.")
    if canid_name_map:
        # longest name length
        name_col_width = max(len(n) for n in canid_name_map.values())
        # add at least 1 space padding
        name_col_width += 1
        print(
            f"Loaded {len(canid_name_map)} CAN ID mappings (name column width: {name_col_width})."
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
            elif key == "q":
                print("\n[QUIT] User requested exit. Shutting down...\n")
                return
            elif key == "r":
                record_mode = not record_mode
                print(
                    f"\n[RECORD] History recording is now {'ON' if record_mode else 'OFF'}.\n"
                )
            elif key == "c":
                change_only_mode = not change_only_mode
                print(f"\n[CHANGED ONLY MODE {'ON' if change_only_mode else 'OFF'}]\n")
            elif key == "d":
                dump_mode = not dump_mode
                if dump_mode:
                    print(
                        f"\n[DUMP MODE ON {'(changes-only!)' if change_only_mode else ''}]\n"
                    )
                else:
                    print("\n[DUMP MODE OFF – returning to histogram]\n")
            elif key == " ":
                clear_screen()

            # Read CAN
            msg = bus.recv(timeout=0.05)
            if msg and match_inverted_filters(msg, inverted_filters):
                update_can_entry(msg)
                if dump_mode:
                    dump_message(msg)

            # Refresh display ~10 times per second
            now = time.time()
            if now - last_refresh > 0.10:
                last_refresh = now

            if dump_mode:
                # Don't refresh whole screen, just print incoming messages
                pass
            elif stats_mode:
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
