import can
import time
import threading
import sys
import termios
import tty

senders = {}
key_pressed = None
binary_mode = False   # toggle with "b"


# ---------------------- Sender Tracking ----------------------

def track_sender(message):
    sender_id = message.arbitration_id
    now = time.time()

    if sender_id not in senders:
        senders[sender_id] = {
            "count": 1,
            "first_seen": now,
            "last_seen": now
        }
        print(f"[NEW SENDER] 0x{sender_id:03X}")
    else:
        senders[sender_id]["count"] += 1
        senders[sender_id]["last_seen"] = now


def print_sender_stats():
    print("\n=========== Sender Stats ===========")
    for sender_id, data in senders.items():
        duration = data["last_seen"] - data["first_seen"]
        freq = data["count"] / duration if duration > 0 else 0.0

        print(f"ID 0x{sender_id:03X}")
        print(f"  Messages: {data['count']}")
        print(f"  First seen: {time.strftime('%H:%M:%S', time.localtime(data['first_seen']))}")
        print(f"  Last seen:  {time.strftime('%H:%M:%S', time.localtime(data['last_seen']))}")
        print(f"  Frequency:  {freq:.2f} msg/sec\n")
    print("====================================\n")


# ---------------------- Keyboard Listener ----------------------

def keyboard_listener():
    global key_pressed
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)
        while True:
            ch = sys.stdin.read(1)
            key_pressed = ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# ---------------------- Data Formatting ----------------------

def format_data_hex(data):
    """Return data bytes as spaced hex: '01 AF 22'."""
    return " ".join(f"{b:02X}" for b in data)


def format_data_bin(data):
    """Return data bytes as spaced 8-bit binary: '01001101 11100010'."""
    return " ".join(f"{b:08b}" for b in data)


def print_message_line(msg):
    """Print one aligned line: ID DLC DATA..."""
    global binary_mode

    data_str = (
        format_data_bin(msg.data)
        if binary_mode
        else format_data_hex(msg.data)
    )

    # Aligned columns: ID(4 chars), DLC(4 chars), DATA(...)
    print(f"{msg.arbitration_id:03X:<4} {msg.dlc:<4} {data_str}")


# ---------------------- Main Program ----------------------

def main():
    global key_pressed, binary_mode

    interface = "can0"

    print(f"Listening on {interface}...")
    print("Press 's' for sender stats, 'b' to toggle hex/binary output, Ctrl+C to exit.\n")

    # Start background keyboard thread
    listener_thread = threading.Thread(target=keyboard_listener, daemon=True)
    listener_thread.start()

    try:
        bus = can.interface.Bus(channel=interface, bustype='socketcan')

        while True:
            # Handle keypress
            if key_pressed == "s":
                print_sender_stats()
                key_pressed = None

            elif key_pressed == "b":
                binary_mode = not binary_mode
                mode = "BINARY" if binary_mode else "HEX"
                print(f"\n[OUTPUT MODE] Now showing data in {mode}\n")
                key_pressed = None

            # Receive CAN message
            msg = bus.recv(timeout=0.2)
            if msg is None:
                continue

            track_sender(msg)
            print_message_line(msg)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except can.CanError as e:
        print(f"CAN error: {e}")


if __name__ == "__main__":
    main()
