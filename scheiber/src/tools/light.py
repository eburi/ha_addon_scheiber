import time
import can
import sys
import os

# Add parent directory to path to import from src
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scheiber import send_burst


def push_light_button(can_interface="can1"):
    """
    Simulate pushing the light button by sending the button press sequence.
    Sends two data packets with a 200ms delay between them.

    Args:
        can_interface: CAN interface name (default "can1")
    """
    # Initialize CAN bus
    bus = can.interface.Bus(channel=can_interface, interface="socketcan")

    try:
        sender_id = "04001A80"

        btn_cockpit_main_pressed_state = "01 54 45 1F 82"
        btn_cockpit_main_released_state = "01 54 45 1F 02"
        btn_understair_port_pressed_state = "01 53 E8 86 83"
        btn_understair_port_released_state = "01 53 E8 86 03"

        data_1 = btn_cockpit_main_pressed_state  # Button pressed state
        data_2 = btn_cockpit_main_released_state  # Button released state

        print("\n[push_light_button] Starting light button push sequence...")

        # Send first packet (button pressed)
        print(f"[push_light_button] Sending packet 1...")
        send_burst(bus, sender_id, data_1, repetitions=3, interval=0.033)

        # Wait 200ms
        print(f"[push_light_button] Waiting 200ms...")
        time.sleep(0.2)

        # Send second packet (button released)
        print(f"[push_light_button] Sending packet 2...")
        send_burst(bus, sender_id, data_2, repetitions=3, interval=0.033)

        print("[push_light_button] Light button push sequence completed.\n")
    finally:
        # Ensure the bus is properly closed
        bus.shutdown()


if __name__ == "__main__":
    import sys

    iface = sys.argv[1] if len(sys.argv) > 1 else "can1"
    push_light_button(iface)
