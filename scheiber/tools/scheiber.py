import time
import threading
import sys
import can


def parse_hex_data(hex_string):
    """Convert hex string (e.g., '01 53 E8 86 83') to bytes."""
    return bytes.fromhex(hex_string.replace(" ", ""))


def sendBurst(bus, senderId, data, repetitions=3, interval=0.033):
    """
    Send CAN data in burst repetitions to simulate a high-priority CAN message.
    
    Args:
        bus: CAN bus instance
        senderId: CAN sender ID (e.g., "04001A80")
        data: Hex data string (e.g., "01 53 E8 86 83")
        repetitions: Number of times to send the data (default 3)
        interval: Time in seconds between repetitions (default 33ms)
    """
    arbitration_id = int(senderId, 16)
    payload = parse_hex_data(data)
    
    for i in range(repetitions):
        msg = can.Message(arbitration_id=arbitration_id, data=payload)
        bus.send(msg)
        print(f"[sendBurst] Sent to {senderId}: {data} (repetition {i+1}/{repetitions})")
        if i < repetitions - 1:
            time.sleep(interval)


def push_light_button(can_interface="can1"):
    """
    Simulate pushing the light button by sending the button press sequence.
    Sends two data packets with a 200ms delay between them.
    
    Args:
        can_interface: CAN interface name (default "can1")
    """
    # Initialize CAN bus
    bus = can.interface.Bus(
        channel=can_interface,
        interface="socketcan"
    )
    
    try:
        sender_id = "04001A80"

        btn_cockpit_main_pressed_state =     "01 54 45 1F 82"
        btn_cockpit_main_released_state =    "01 54 45 1F 02"
        btn_understair_port_pressed_state =  "01 53 E8 86 83"
        btn_understair_port_released_state = "01 53 E8 86 03"

        data_1 = btn_cockpit_main_pressed_state  # Button pressed state
        data_2 = btn_cockpit_main_released_state  # Button released state
        
        print("\n[push_light_button] Starting light button push sequence...")
        
        # Send first packet (button pressed)
        print(f"[push_light_button] Sending packet 1...")
        sendBurst(bus, sender_id, data_1, repetitions=3, interval=0.033)
        
        # Wait 200ms
        print(f"[push_light_button] Waiting 200ms...")
        time.sleep(0.2)
        
        # Send second packet (button released)
        print(f"[push_light_button] Sending packet 2...")
        sendBurst(bus, sender_id, data_2, repetitions=3, interval=0.033)
        
        print("[push_light_button] Light button push sequence completed.\n")
    finally:
        # Ensure the bus is properly closed
        bus.shutdown()


if __name__ == "__main__":
    # Get CAN interface from command line argument, default to "can1"
    can_interface = sys.argv[1] if len(sys.argv) > 1 else "can1"
    
    # Example usage
    push_light_button(can_interface)
