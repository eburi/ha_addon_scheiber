#!/usr/bin/env python3
"""
Analyze all CAN bus messages to find correlation with Bloc9 switch state changes.

This tool monitors CAN bus for:
1. Switch state changes (S1-S6 on/off and brightness)
2. ALL other messages on the bus to find correlations

Goal: Determine if any CAN messages reliably correlate with switch state changes
      and could be used to predict/track the current state of the system.

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

        # Track ALL messages seen on the bus
        # Format: {arb_id: {'last_data': bytes, 'last_timestamp': float, 'change_count': int}}
        self.all_messages = {}

        # Track messages that changed around switch events
        # Format: [(change_event, messages_snapshot_before, messages_snapshot_after), ...]
        self.correlations = []

        # Pending switch change (waiting for subsequent messages)
        self.pending_change = None
        self.pending_change_time = None
        self.messages_after_change = []

        # Time window to collect messages after a switch change (seconds)
        self.collection_window = 2.0

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
        """Record a switch state change and start collecting subsequent messages."""
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

        # Take snapshot of all current message states
        messages_before = {
            arb_id: dict(info) for arb_id, info in self.all_messages.items()
        }

        # Record this change event
        change_event = {
            "timestamp": timestamp,
            "bloc9_id": bloc9_id,
            "switch": switch_nr,
            "property": property_name,
            "old_value": old_value,
            "new_value": new_value,
            "messages_before": messages_before,
        }

        # Start collecting messages after this change
        self.pending_change = change_event
        self.pending_change_time = timestamp
        self.messages_after_change = []

        # Print change notification
        dt = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S.%f")[:-3]
        print(
            f"\n[{dt}] Bloc9 #{bloc9_id} - {switch_nr} {property_name}: {old_value} -> {new_value}"
        )
        print(
            f"    Collecting messages for {self.collection_window}s to find correlations..."
        )

    def check_pending_collection(self, current_time):
        """Check if we've finished collecting messages after a switch change."""
        if self.pending_change and self.pending_change_time:
            elapsed = current_time - self.pending_change_time
            if elapsed >= self.collection_window:
                # Collection period is over, analyze correlations
                self.finalize_correlation()

    def finalize_correlation(self):
        """Finalize the correlation analysis for a pending switch change."""
        if not self.pending_change:
            return

        change = self.pending_change
        messages_before = change["messages_before"]

        # Find messages that changed during the collection window
        changed_messages = []
        for arb_id, current_info in self.all_messages.items():
            before_info = messages_before.get(arb_id)

            if before_info is None:
                # New message that appeared after the switch change
                changed_messages.append(
                    {
                        "arb_id": arb_id,
                        "type": "new",
                        "data_after": current_info["last_data"],
                    }
                )
            elif before_info["last_data"] != current_info["last_data"]:
                # Existing message that changed
                changed_messages.append(
                    {
                        "arb_id": arb_id,
                        "type": "changed",
                        "data_before": before_info["last_data"],
                        "data_after": current_info["last_data"],
                    }
                )

        # Save correlation
        self.correlations.append(
            {
                "change": change,
                "changed_messages": changed_messages,
            }
        )

        # Print summary
        if changed_messages:
            print(f"    Found {len(changed_messages)} message(s) that changed:")
            for msg in changed_messages[:5]:  # Show first 5
                if msg["type"] == "new":
                    print(
                        f"      NEW: 0x{msg['arb_id']:08X} = {self.format_bytes(msg['data_after'])}"
                    )
                else:
                    print(f"      CHG: 0x{msg['arb_id']:08X}")
                    print(f"           Before: {self.format_bytes(msg['data_before'])}")
                    print(f"           After:  {self.format_bytes(msg['data_after'])}")
            if len(changed_messages) > 5:
                print(f"      ... and {len(changed_messages) - 5} more")
        else:
            print(f"    No other messages changed during collection window")

        # Clear pending
        self.pending_change = None
        self.pending_change_time = None
        self.messages_after_change = []
        print()

    def run(self):
        """Main analysis loop."""
        print(f"Starting Bloc9 Correlation Analyzer on {self.can_interface}")
        if self.target_bloc9_id is not None:
            print(f"Filtering for Bloc9 ID: {self.target_bloc9_id}")
        print("\nListening for switch changes and ALL bus messages...")
        print("Perform switch operations to see which messages correlate.\n")
        print("Press Ctrl+C to stop and see summary.\n")

        try:
            self.bus = can.interface.Bus(
                channel=self.can_interface, interface="socketcan"
            )

            # Track last seen values to detect changes
            last_values = {}

            while True:
                msg = self.bus.recv(timeout=0.1)
                current_time = time.time()

                # Check if we need to finalize a pending collection
                self.check_pending_collection(current_time)

                if msg is None:
                    continue

                arb = msg.arbitration_id
                data = bytes(msg.data)

                # Track ALL messages
                if arb not in self.all_messages:
                    self.all_messages[arb] = {
                        "last_data": data,
                        "last_timestamp": current_time,
                        "change_count": 0,
                    }
                else:
                    if self.all_messages[arb]["last_data"] != data:
                        self.all_messages[arb]["change_count"] += 1
                    self.all_messages[arb]["last_data"] = data
                    self.all_messages[arb]["last_timestamp"] = current_time

                # Try to decode Bloc9 messages
                device_key, device_config, matcher, bus_id = find_device_and_matcher(
                    arb
                )

                if device_key != "bloc9":
                    continue

                # Filter by target Bloc9 ID if specified
                if self.target_bloc9_id is not None and bus_id != self.target_bloc9_id:
                    continue

                # Handle switch state messages (not the generic status update)
                if (
                    matcher
                    and "Status update" in matcher["name"]
                    and matcher["name"] != "Status update"
                ):
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
            f"Observed {len(self.correlations)} switch change(s) with message correlations:\n"
        )

        # Collect statistics about which messages change most frequently with switches
        message_correlation_count = (
            {}
        )  # arb_id -> count of times it changed with a switch

        for idx, corr in enumerate(self.correlations, 1):
            change = corr["change"]
            changed_messages = corr["changed_messages"]

            print(
                f"{idx}. Bloc9 #{change['bloc9_id']} - {change['switch']} {change['property']}: "
                f"{change['old_value']} -> {change['new_value']}"
            )
            print(
                f"   {len(changed_messages)} message(s) changed within {self.collection_window}s:"
            )

            for msg in changed_messages:
                arb_id = msg["arb_id"]
                message_correlation_count[arb_id] = (
                    message_correlation_count.get(arb_id, 0) + 1
                )

                if msg["type"] == "new":
                    print(
                        f"     NEW: 0x{arb_id:08X} = {self.format_bytes(msg['data_after'])}"
                    )
                else:
                    print(f"     CHG: 0x{arb_id:08X}")
                    print(f"          Before: {self.format_bytes(msg['data_before'])}")
                    print(f"          After:  {self.format_bytes(msg['data_after'])}")
                    self.print_status_diff(msg["data_before"], msg["data_after"])
            print()

        # Analysis
        print("\n=== Pattern Analysis ===\n")

        if message_correlation_count:
            print("Messages that consistently correlate with switch changes:\n")
            # Sort by correlation count
            sorted_correlations = sorted(
                message_correlation_count.items(), key=lambda x: x[1], reverse=True
            )

            for arb_id, count in sorted_correlations:
                percentage = (count / len(self.correlations)) * 100
                print(
                    f"  0x{arb_id:08X}: Changed in {count}/{len(self.correlations)} events ({percentage:.0f}%)"
                )

                # Try to identify the message type
                device_key, device_config, matcher, bus_id = find_device_and_matcher(
                    arb_id
                )
                if device_key and matcher:
                    print(
                        f"    → {device_config['name']} (ID {bus_id}): {matcher['name']}"
                    )
                else:
                    print(f"    → Unknown message type")

            print("\n✓ Found messages that correlate with switch state changes!")
            print("  These messages could potentially be used to track system state.")
        else:
            print("✗ No messages reliably correlate with switch state changes.")
            print("  The system may not broadcast state information on the CAN bus.")

        # Show total unique messages seen
        print(f"\nTotal unique CAN messages observed: {len(self.all_messages)}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze all CAN bus messages for correlation with Bloc9 switch state changes",
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
