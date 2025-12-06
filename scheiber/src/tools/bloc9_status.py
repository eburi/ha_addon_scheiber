#!/usr/bin/env python3
"""
Analyze Bloc9 "Status update" messages to find correlation with switch states.

This tool monitors CAN bus for:
1. Switch state changes (S1-S6 on/off and brightness)
2. General status update messages (0x00000600 prefix)

Goal: Determine if switch states can be deduced from status update messages.

Usage:
  python bloc9_status.py <can_interface> [bloc9_id]

Example:
  python bloc9_status.py can1 10
"""

import argparse
import os
import sys
import time
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import can
from can_decoder import extract_property_value, find_device_and_matcher


class Bloc9StatusAnalyzer:
    def __init__(self, can_interface, target_bloc9_id=None):
        self.can_interface = can_interface
        self.target_bloc9_id = target_bloc9_id
        self.bus = None

        # Track current switch states for each Bloc9
        # Format: {bloc9_id: {'s1': {'state': bool, 'brightness': int}, ...}}
        self.switch_states = {}

        # Track last status update for each Bloc9
        # Format: {bloc9_id: {'data': bytes, 'timestamp': float}}
        self.last_status = {}

        # Track status updates after switch changes
        # Format: [(change_event, status_before, status_after), ...]
        self.correlations = []

        # Pending switch change (waiting for next status update)
        self.pending_change = None

    def extract_bloc9_id(self, arb_id):
        """Extract Bloc9 ID from arbitration ID."""
        low_byte = arb_id & 0xFF
        if low_byte & 0x80:
            return (low_byte & ~0x80) >> 3
        return None

    def format_bytes(self, data):
        """Format bytes as hex string."""
        return " ".join(f"{b:02X}" for b in data)

    def format_bits(self, data):
        """Format bytes as binary string with bit positions."""
        result = []
        for byte_idx, byte_val in enumerate(data):
            bits = f"{byte_val:08b}"
            result.append(f"B{byte_idx}:{bits}")
        return " | ".join(result)

    def print_status_diff(self, old_data, new_data):
        """Print differences between two status messages."""
        if old_data == new_data:
            print("      [No change in status message]")
            return

        print("      Status message changed:")
        for byte_idx in range(min(len(old_data), len(new_data))):
            if old_data[byte_idx] != new_data[byte_idx]:
                old_bits = f"{old_data[byte_idx]:08b}"
                new_bits = f"{new_data[byte_idx]:08b}"
                print(
                    f"        Byte {byte_idx}: {old_bits} -> {new_bits} (0x{old_data[byte_idx]:02X} -> 0x{new_data[byte_idx]:02X})"
                )

                # Show which bits changed
                changed_bits = []
                for bit_idx in range(8):
                    old_bit = (old_data[byte_idx] >> bit_idx) & 1
                    new_bit = (new_data[byte_idx] >> bit_idx) & 1
                    if old_bit != new_bit:
                        changed_bits.append(f"bit{bit_idx}: {old_bit}->{new_bit}")
                if changed_bits:
                    print(f"          Changed: {', '.join(changed_bits)}")

    def analyze_switch_change(
        self, bloc9_id, switch_nr, property_name, old_value, new_value
    ):
        """Record a switch state change and prepare for status correlation."""
        timestamp = time.time()

        # Initialize switch state tracking if needed
        if bloc9_id not in self.switch_states:
            self.switch_states[bloc9_id] = {
                f"s{i}": {"state": None, "brightness": None} for i in range(1, 7)
            }

        # Update tracked state
        if "brightness" in property_name:
            self.switch_states[bloc9_id][switch_nr]["brightness"] = new_value
        else:
            self.switch_states[bloc9_id][switch_nr]["state"] = new_value

        # Get status before change
        status_before = self.last_status.get(bloc9_id, {}).get("data")

        # Record this change event
        change_event = {
            "timestamp": timestamp,
            "bloc9_id": bloc9_id,
            "switch": switch_nr,
            "property": property_name,
            "old_value": old_value,
            "new_value": new_value,
            "status_before": status_before,
        }

        # Store as pending (we'll complete it when next status arrives)
        self.pending_change = change_event

        # Print change notification
        dt = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S.%f")[:-3]
        print(
            f"\n[{dt}] Bloc9 #{bloc9_id} - {switch_nr} {property_name}: {old_value} -> {new_value}"
        )
        if status_before:
            print(f"    Status before: {self.format_bytes(status_before)}")
            print(f"    Bits:          {self.format_bits(status_before)}")
        else:
            print(f"    Status before: [Not yet seen]")
        print(f"    Waiting for next status update...")

    def process_status_update(self, bloc9_id, data):
        """Process a status update message."""
        timestamp = time.time()

        # Check if we have a pending switch change
        if self.pending_change and self.pending_change["bloc9_id"] == bloc9_id:
            # Complete the correlation
            change = self.pending_change
            status_after = data

            print(f"    Status after:  {self.format_bytes(status_after)}")
            print(f"    Bits:          {self.format_bits(status_after)}")

            if change["status_before"]:
                self.print_status_diff(change["status_before"], status_after)
            else:
                print(f"      [First status message seen]")

            # Save correlation
            self.correlations.append(
                {
                    "change": change,
                    "status_after": status_after,
                }
            )

            # Clear pending
            self.pending_change = None
            print()

        # Update last seen status
        self.last_status[bloc9_id] = {
            "data": data,
            "timestamp": timestamp,
        }

    def run(self):
        """Main analysis loop."""
        print(f"Starting Bloc9 Status Analyzer on {self.can_interface}")
        if self.target_bloc9_id is not None:
            print(f"Filtering for Bloc9 ID: {self.target_bloc9_id}")
        print("\nListening for switch changes and status updates...")
        print("Perform switch operations to see correlation with status messages.\n")
        print("Press Ctrl+C to stop and see summary.\n")

        try:
            self.bus = can.interface.Bus(
                channel=self.can_interface, interface="socketcan"
            )

            # Track last seen values to detect changes
            last_values = {}

            while True:
                msg = self.bus.recv(timeout=1.0)
                if msg is None:
                    continue

                arb = msg.arbitration_id
                data = bytes(msg.data)

                # Try to decode the message
                device_key, device_config, matcher, bus_id = find_device_and_matcher(
                    arb
                )

                if device_key != "bloc9":
                    continue

                # Filter by target Bloc9 ID if specified
                if self.target_bloc9_id is not None and bus_id != self.target_bloc9_id:
                    continue

                # Handle status update messages
                if matcher and matcher["name"] == "Status update":
                    self.process_status_update(bus_id, data)
                    continue

                # Handle switch state messages
                if matcher and "Status update" in matcher["name"]:
                    # Decode properties
                    properties = matcher.get("properties", {})
                    for prop_name, prop_config in properties.items():
                        if prop_config is None:
                            continue

                        template = prop_config.get("template")
                        value = extract_property_value(data, template)

                        # Track changes
                        key = (bus_id, prop_name)
                        old_value = last_values.get(key)

                        if old_value is not None and old_value != value:
                            # Detect which switch this is
                            if prop_name.startswith("s") and len(prop_name) >= 2:
                                switch_nr = prop_name[:2]  # 's1', 's2', etc.
                                self.analyze_switch_change(
                                    bus_id, switch_nr, prop_name, old_value, value
                                )

                        last_values[key] = value

        except KeyboardInterrupt:
            print("\n\n=== Analysis Summary ===\n")
            self.print_summary()
        finally:
            if self.bus:
                self.bus.shutdown()

    def print_summary(self):
        """Print analysis summary."""
        if not self.correlations:
            print("No switch changes were observed during monitoring.")
            return

        print(
            f"Observed {len(self.correlations)} switch change(s) with status correlations:\n"
        )

        for idx, corr in enumerate(self.correlations, 1):
            change = corr["change"]
            status_after = corr["status_after"]

            print(
                f"{idx}. Bloc9 #{change['bloc9_id']} - {change['switch']} {change['property']}: "
                f"{change['old_value']} -> {change['new_value']}"
            )

            if change["status_before"]:
                print(f"   Before: {self.format_bytes(change['status_before'])}")
                print(f"   After:  {self.format_bytes(status_after)}")
                self.print_status_diff(change["status_before"], status_after)
            else:
                print(f"   After:  {self.format_bytes(status_after)}")
                print(f"   (No 'before' status available)")
            print()

        # Analysis
        print("\n=== Pattern Analysis ===\n")

        # Check if status messages ever change
        has_changes = False
        for corr in self.correlations:
            if (
                corr["change"]["status_before"]
                and corr["change"]["status_before"] != corr["status_after"]
            ):
                has_changes = True
                break

        if has_changes:
            print("✓ Status update messages DO change when switches are operated.")
            print("  Further analysis needed to decode the relationship.")
        else:
            print("✗ Status update messages do NOT change when switches are operated.")
            print("  The 0x00000600 messages appear to be unrelated to switch states.")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Bloc9 status update messages for switch state correlation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "can_interface",
        help="CAN interface name (e.g., can0, can1)",
    )
    parser.add_argument(
        "bloc9_id",
        type=int,
        nargs="?",
        help="Optional: Filter for specific Bloc9 ID (e.g., 10)",
    )

    args = parser.parse_args()

    analyzer = Bloc9StatusAnalyzer(args.can_interface, args.bloc9_id)
    analyzer.run()


if __name__ == "__main__":
    main()
