import time
import threading
import sys
import can


def parse_hex_data(hex_string):
    """Convert hex string (e.g., '01 53 E8 86 83') to bytes."""
    return bytes.fromhex(hex_string.replace(" ", ""))


def bloc9_switch(can_interface, bloc9_id, switch_nr, state):
    """
    Send a Bloc9 switch command via CAN bus.
    
    Args:
        bus: CAN bus instance
        bloc9_id: Bloc9 device ID (number)
        switch_nr: Switch number (number)
        state: Boolean state (True for ON, False for OFF)
    
    Constructs CAN ID as follows:
    - Shift bloc9_id left by 3 bits
    - Set the most significant bit to 1
    - Use that byte as the lowest byte in 0x02360600
    
    Constructs 4-byte body:
    - Byte 0: switch_nr
    - Byte 1: 0x01 if state is True, 0x00 if False
    - Byte 2: 0x00
    - Byte 3: 0x00
    
    Example: bloc9_id=10, switch_nr=3, state=True -> CAN ID: 0x023606D0, Data: 03 01 00 00
    """
    # Open CAN bus, construct CAN ID and data, send, then close bus
    bus = can.interface.Bus(channel=can_interface, interface="socketcan")
    try:
        # Construct CAN ID
        shifted = (bloc9_id << 3) | 0x80
        can_id = 0x02360600 | shifted

        # Construct 4-byte body
        state_byte = 0x01 if state else 0x00
        data = bytes([switch_nr, state_byte, 0x00, 0x00])

        # Send the message
        msg = can.Message(arbitration_id=can_id, data=data)
        bus.send(msg)
        print(f"[bloc9_switch] Sent to ID 0x{can_id:08X}: {' '.join(f'{b:02X}' for b in data)}")
    finally:
        # Ensure the bus is properly closed
        bus.shutdown()


def send_burst(bus, sender_id, data, repetitions=3, interval=0.033):
    """
    Send CAN data in burst repetitions to simulate a high-priority CAN message.
    
    Args:
        bus: CAN bus instance
        sender_id: CAN sender ID (e.g., "04001A80")
        data: Hex data string (e.g., "01 53 E8 86 83")
        repetitions: Number of times to send the data (default 3)
        interval: Time in seconds between repetitions (default 33ms)
    """
    arbitration_id = int(sender_id, 16)
    payload = parse_hex_data(data)
    
    for i in range(repetitions):
        msg = can.Message(arbitration_id=arbitration_id, data=payload)
        bus.send(msg)
        print(f"[send_burst] Sent to {sender_id}: {data} (repetition {i+1}/{repetitions})")
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


def test_switch(bus_nr, switch_nr, can_interface="can1"):
    """
    Test toggling a switch on a Bloc9 device by calling `bloc9_switch`.
    """
    try:
        bloc9_switch(can_interface, int(bus_nr), int(switch_nr), True)

        # Wait 1s
        print("turn on wait 1s...")
        time.sleep(1)

        bloc9_switch(can_interface, int(bus_nr), int(switch_nr), False)
    except Exception as e:
        print(f"[test_switch] Error: {e}")



if __name__ == "__main__":
    # Get CAN interface from command line argument, default to "can1"
    switch_nr = sys.argv[1] if len(sys.argv) > 1 else "3"
    bus_nr = sys.argv[2] if len(sys.argv) > 2 else "7"
    
    # Example usage
    # push_light_button(can_interface)

    test_switch(bus_nr, switch_nr, can_interface="can1")
