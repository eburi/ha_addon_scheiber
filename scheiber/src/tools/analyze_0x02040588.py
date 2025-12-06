#!/usr/bin/env python3
"""
Analyze 0x02040588 messages and their correlation with bloc9 switch changes.

This tool focuses on understanding the bit patterns in 0x02040588 messages
and how the bus_id might be encoded in the arbitration ID.

Usage:
    python analyze_0x02040588.py <can_interface>

Example:
    python analyze_0x02040588.py can1
"""

import argparse
import os
import sys
import time
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import can
from can_decoder import find_device_and_matcher


class Message0x02040588Analyzer:
    """Analyzer for 0x02040588 messages and their patterns."""

    def __init__(self, can_interface: str):
        self.can_interface = can_interface
        self.can_bus = None

        # Track messages by arbitration ID
        self.messages = defaultdict(
            lambda: {"last_data": None, "count": 0, "changes": []}
        )

        # Focus on our target message
        self.target_id = 0x02040588

        # Track bloc9 switch state changes
        self.bloc9_changes = []

        # Track last seen state for each bloc9 device
        self.last_bloc9_state = {}

    def analyze_arbitration_id(self, arb_id: int):
        """Analyze the structure of the arbitration ID."""
        print(f"\n=== Arbitration ID Analysis: 0x{arb_id:08X} ===")
        print(f"Binary: {arb_id:029b}")
        print(f"Hex:    0x{arb_id:08X}")

        # Break it down into potential components
        print("\nByte breakdown:")
        byte3 = (arb_id >> 24) & 0xFF
        byte2 = (arb_id >> 16) & 0xFF
        byte1 = (arb_id >> 8) & 0xFF
        byte0 = arb_id & 0xFF

        print(f"  Byte 3 (MSB): 0x{byte3:02X} = {byte3:08b} (decimal: {byte3})")
        print(f"  Byte 2:       0x{byte2:02X} = {byte2:08b} (decimal: {byte2})")
        print(f"  Byte 1:       0x{byte1:02X} = {byte1:08b} (decimal: {byte1})")
        print(f"  Byte 0 (LSB): 0x{byte0:02X} = {byte0:08b} (decimal: {byte0})")

        # Try to extract potential bus_id patterns
        print("\nPotential bus_id extraction methods:")

        # Method 1: Lower 3 bits of lowest byte
        bus_id_1 = byte0 & 0x07
        print(f"  Method 1 (byte0 & 0x07):           {bus_id_1}")

        # Method 2: Lower 4 bits of lowest byte
        bus_id_2 = byte0 & 0x0F
        print(f"  Method 2 (byte0 & 0x0F):           {bus_id_2}")

        # Method 3: Entire lowest byte right-shifted 3
        bus_id_3 = byte0 >> 3
        print(f"  Method 3 (byte0 >> 3):             {bus_id_3}")

        # Method 4: Lower 5 bits of lowest byte
        bus_id_4 = byte0 & 0x1F
        print(f"  Method 4 (byte0 & 0x1F):           {bus_id_4}")

        # Method 5: Lowest byte XOR with 0x80
        bus_id_5 = (byte0 ^ 0x80) >> 3
        print(f"  Method 5 ((byte0 ^ 0x80) >> 3):   {bus_id_5}")

        # Compare with known bloc9 pattern for 0x023606D0 (bloc9 #10)
        print("\nComparison with known bloc9 pattern (0x023606D0 = bloc9 #10):")
        known_bloc9_id = 0x023606D0
        known_byte0 = known_bloc9_id & 0xFF
        print(f"  Known: 0x{known_bloc9_id:08X}, byte0=0x{known_byte0:02X}, bus_id=10")
        print(
            f"  Formula: (0x{known_byte0:02X} ^ 0x80) >> 3 = {(known_byte0 ^ 0x80) >> 3}"
        )

        # For 0x02040588
        print(f"\n  Target: 0x{arb_id:08X}, byte0=0x{byte0:02X}")
        print(
            f"  Using same formula: (0x{byte0:02X} ^ 0x80) >> 3 = {(byte0 ^ 0x80) >> 3}"
        )

        # Check if bit pattern suggests specific meaning
        print(f"\nBit 7 of byte0: {(byte0 >> 7) & 1} (0x80 flag)")
        print(f"Bits 3-6 of byte0: {(byte0 >> 3) & 0x0F}")
        print(f"Bits 0-2 of byte0: {byte0 & 0x07}")

    def analyze_data_pattern(self, data: bytes):
        """Analyze the data payload pattern."""
        print("\n=== Data Payload Analysis ===")
        print(f"Length: {len(data)} bytes")
        print(f"Hex:    {' '.join(f'{b:02X}' for b in data)}")
        print(f"Binary:")
        for i, byte in enumerate(data):
            print(f"  Byte {i}: {byte:08b} (0x{byte:02X}, decimal: {byte})")

        # Look for patterns
        print("\nPotential interpretations:")
        if len(data) >= 8:
            print(f"  Bytes 0-1 as uint16: {int.from_bytes(data[0:2], 'big')}")
            print(f"  Bytes 2-3 as uint16: {int.from_bytes(data[2:4], 'big')}")
            print(f"  Bytes 4-5 as uint16: {int.from_bytes(data[4:6], 'big')}")
            print(f"  Bytes 6-7 as uint16: {int.from_bytes(data[6:8], 'big')}")

    def compare_data(self, before: bytes, after: bytes):
        """Compare two data payloads and show what changed."""
        print("\n=== Data Change Analysis ===")
        print(f"Before: {' '.join(f'{b:02X}' for b in before)}")
        print(f"After:  {' '.join(f'{b:02X}' for b in after)}")

        changes = []
        for i, (b1, b2) in enumerate(zip(before, after)):
            if b1 != b2:
                print(f"\nByte {i} changed: 0x{b1:02X} -> 0x{b2:02X}")
                print(f"  Binary: {b1:08b} -> {b2:08b}")

                # Show bit-level changes
                xor = b1 ^ b2
                changed_bits = []
                for bit in range(8):
                    if xor & (1 << bit):
                        old_val = (b1 >> bit) & 1
                        new_val = (b2 >> bit) & 1
                        changed_bits.append(f"bit{bit}: {old_val}->{new_val}")

                print(f"  Changed bits: {', '.join(changed_bits)}")
                changes.append((i, b1, b2, changed_bits))

        return changes

    def track_message(self, arb_id: int, data: bytes, timestamp: float):
        """Track a message and detect changes."""
        msg_info = self.messages[arb_id]
        msg_info["count"] += 1

        if msg_info["last_data"] is not None and msg_info["last_data"] != data:
            change_info = {
                "timestamp": timestamp,
                "before": msg_info["last_data"],
                "after": data,
                "arb_id": arb_id,
            }
            msg_info["changes"].append(change_info)

            # If this is our target message, analyze it
            if arb_id == self.target_id:
                print(f"\n{'='*60}")
                print(f"0x02040588 MESSAGE CHANGED at {timestamp:.2f}s")
                print(f"{'='*60}")
                self.compare_data(msg_info["last_data"], data)

        msg_info["last_data"] = data

    def track_bloc9_state(
        self, device_key: str, bus_id: int, properties: dict, timestamp: float
    ):
        """Track bloc9 device state and detect switch changes."""
        state_key = (device_key, bus_id)

        # Get switch states (s1-s6)
        current_switches = {
            k: v
            for k, v in properties.items()
            if k.startswith("s") and not k.endswith("_brightness")
        }

        if state_key not in self.last_bloc9_state:
            self.last_bloc9_state[state_key] = current_switches
            return

        # Check for changes
        last_switches = self.last_bloc9_state[state_key]
        for switch_name, current_value in current_switches.items():
            last_value = last_switches.get(switch_name)
            if last_value != current_value:
                change_info = {
                    "timestamp": timestamp,
                    "device": f"Bloc9 #{bus_id}",
                    "switch": switch_name,
                    "old_value": last_value,
                    "new_value": current_value,
                }
                self.bloc9_changes.append(change_info)

                print(f"\n{'='*60}")
                print(f"BLOC9 SWITCH CHANGE at {timestamp:.2f}s")
                print(f"Device: Bloc9 #{bus_id}, Switch: {switch_name}")
                print(f"Value: {last_value} -> {current_value}")
                print(f"{'='*60}")

        self.last_bloc9_state[state_key] = current_switches

    def correlate_changes(self):
        """Correlate 0x02040588 changes with bloc9 switch changes."""
        print("\n\n" + "=" * 80)
        print("CORRELATION ANALYSIS")
        print("=" * 80)

        target_changes = self.messages[self.target_id]["changes"]

        print(f"\nTotal 0x02040588 changes: {len(target_changes)}")
        print(f"Total bloc9 switch changes: {len(self.bloc9_changes)}")

        # For each bloc9 change, find nearby 0x02040588 changes
        correlation_window = 2.0  # seconds

        for i, bloc9_change in enumerate(self.bloc9_changes, 1):
            print(f"\n--- Bloc9 Change #{i} ---")
            print(f"Time: {bloc9_change['timestamp']:.2f}s")
            print(
                f"{bloc9_change['device']} - {bloc9_change['switch']}: {bloc9_change['old_value']} -> {bloc9_change['new_value']}"
            )

            # Find 0x02040588 changes within window
            nearby_changes = []
            for msg_change in target_changes:
                time_diff = abs(msg_change["timestamp"] - bloc9_change["timestamp"])
                if time_diff <= correlation_window:
                    nearby_changes.append((time_diff, msg_change))

            if nearby_changes:
                print(
                    f"\nFound {len(nearby_changes)} 0x02040588 change(s) within {correlation_window}s:"
                )
                for time_diff, msg_change in sorted(nearby_changes):
                    print(f"\n  [{time_diff:+.3f}s] 0x02040588 changed:")
                    self.compare_data(msg_change["before"], msg_change["after"])
            else:
                print(f"\nNo 0x02040588 changes within {correlation_window}s")

    def run(self):
        """Main analysis loop."""
        print("=" * 80)
        print("0x02040588 Message Analyzer")
        print("=" * 80)

        # First, analyze the arbitration ID structure
        self.analyze_arbitration_id(self.target_id)

        print("\n\nStarting live CAN bus monitoring...")
        print("Press Ctrl+C to stop and see correlation analysis\n")

        try:
            self.can_bus = can.interface.Bus(
                channel=self.can_interface, interface="socketcan"
            )

            start_time = time.time()

            while True:
                msg = self.can_bus.recv(timeout=1.0)
                if msg is None:
                    continue

                timestamp = time.time() - start_time
                arb_id = msg.arbitration_id
                data = bytes(msg.data)

                # Track all messages
                self.track_message(arb_id, data, timestamp)

                # Check if this is a bloc9 message and decode it
                device_key, device_config, matcher, bus_id = find_device_and_matcher(
                    arb_id
                )

                if device_key == "bloc9" and matcher:
                    # Decode the message
                    from can_decoder import extract_property_value

                    properties = {}
                    for prop_name, prop_config in matcher.get("properties", {}).items():
                        if prop_config:
                            template = prop_config.get("template")
                            value = extract_property_value(data, template)
                            if value is not None:
                                properties[prop_name] = value

                    self.track_bloc9_state(device_key, bus_id, properties, timestamp)

        except KeyboardInterrupt:
            print("\n\nStopping...")
        finally:
            if self.can_bus:
                self.can_bus.shutdown()

        # Show correlation analysis
        self.correlate_changes()

        # Summary statistics
        print("\n\n" + "=" * 80)
        print("SUMMARY STATISTICS")
        print("=" * 80)

        target_info = self.messages[self.target_id]
        print(f"\n0x02040588 messages:")
        print(f"  Total received: {target_info['count']}")
        print(f"  Total changes: {len(target_info['changes'])}")

        if target_info["last_data"]:
            print(f"\n  Last data seen:")
            self.analyze_data_pattern(target_info["last_data"])


def main():
    parser = argparse.ArgumentParser(
        description="Analyze 0x02040588 messages and correlate with bloc9 changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "can_interface",
        help="CAN interface name (e.g., can0, can1)",
    )

    args = parser.parse_args()

    analyzer = Message0x02040588Analyzer(args.can_interface)
    analyzer.run()


if __name__ == "__main__":
    main()
