import time
import threading
import sys
import can
import os
import re
from collections import defaultdict


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


if __name__ == "__main__":
    # Get CAN interface from command line argument, default to "can1"
    switch_nr = sys.argv[1] if len(sys.argv) > 1 else "3"
    bus_nr = sys.argv[2] if len(sys.argv) > 2 else "7"
    state = sys.argv[3] if len(sys.argv) > 3 else "ON"
    
    # Example usage
    # push_light_button(can_interface)
    print(f"[main] Toggling switch {switch_nr} on bus {bus_nr} to {'ON' if state != 'OFF' else 'OFF'}")
    bloc9_switch("can1", int(bus_nr), int(switch_nr), state)
