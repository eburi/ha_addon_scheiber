#!/usr/bin/env python3
"""
Helper script to analyze CAN messages and identify dimming level patterns.

Usage:
  python analyze_dimming.py can1

Instructions:
  1. Run this script while monitoring a CAN interface
  2. Adjust dimming levels on the physical switches
  3. Watch the output to identify which bytes change with dimming
  4. Once patterns are identified, update device_types.yaml

The script shows:
  - Full hex dump with byte indices for each message
  - Byte-by-byte diff when messages change
  - Correlation analysis to help identify dimming bytes
"""

import sys
import can
from collections import defaultdict
import os

# Add parent directory to path to import from src
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from canlistener import find_device_and_matcher


def analyze_dimming(can_interface="can1"):
    """Listen and show detailed byte-level analysis for dimming identification."""

    last_seen = {}
    byte_changes = defaultdict(
        lambda: defaultdict(list)
    )  # Track which bytes change per device

    bus = can.interface.Bus(channel=can_interface, interface="socketcan")
    try:
        print(f"Analyzing dimming on {can_interface}")
        print("Adjust dimming levels and watch for byte changes...\n")

        while True:
            msg = bus.recv(timeout=1.0)
            if msg is None:
                continue

            arb = msg.arbitration_id
            device_key, device_config, matcher, bus_id = find_device_and_matcher(arb)

            if device_config is None or matcher is None:
                continue

            raw = bytes(msg.data)

            id_triple = (device_key, bus_id, matcher["name"])
            prev = last_seen.get(id_triple)

            # Show hex dump with indices
            hex_dump = " ".join(f"{i}:{b:02X}" for i, b in enumerate(raw))

            if prev is None:
                print(
                    f"\n{device_config['name']} ID:{bus_id} [{matcher['name']}] [FIRST SEEN]"
                )
                print(f"  HEX: {hex_dump}")
                last_seen[id_triple] = raw
                continue

            if prev != raw:
                print(
                    f"\n{device_config['name']} ID:{bus_id} [{matcher['name']}] [CHANGED]"
                )
                print(f"  HEX: {hex_dump}")

                # Show byte-by-byte diff
                diffs = []
                for i, (old_byte, new_byte) in enumerate(zip(prev, raw)):
                    if old_byte != new_byte:
                        diffs.append(
                            f"byte[{i}]: 0x{old_byte:02X}→0x{new_byte:02X} ({old_byte}→{new_byte})"
                        )
                        byte_changes[id_triple][i].append((old_byte, new_byte))

                if diffs:
                    print("  DIFF: " + ", ".join(diffs))

                    # Suggest potential dimming bytes (those that change frequently)
                    for byte_idx in sorted(
                        set(i for i in range(len(raw)) if prev[i] != raw[i])
                    ):
                        changes = byte_changes[id_triple][byte_idx]
                        if len(changes) >= 2:
                            values = sorted(set(new for old, new in changes))
                            if len(values) > 2:  # More than just on/off
                                print(
                                    f"  → byte[{byte_idx}] might be dimming (values seen: {values})"
                                )

                last_seen[id_triple] = raw

    except KeyboardInterrupt:
        print("\n\nAnalysis Summary:")
        print("=" * 60)

        for id_triple, byte_dict in byte_changes.items():
            device_key, bus_id, matcher_name = id_triple
            print(f"\n{device_key} ID:{bus_id} [{matcher_name}]:")

            for byte_idx in sorted(byte_dict.keys()):
                changes = byte_dict[byte_idx]
                unique_values = sorted(set(new for old, new in changes))
                print(
                    f"  byte[{byte_idx}]: {len(changes)} changes, values: {unique_values}"
                )

                # If many unique values, likely dimming
                if len(unique_values) > 2:
                    print(
                        f"    ⚠ LIKELY DIMMING BYTE (range: {min(unique_values)}-{max(unique_values)})"
                    )
                    print(
                        f"    Add to properties: 'sN_dim': {{'template': '[{byte_idx}]', 'formatter': 'SN_DIM={{}}'}}"
                    )

        print("\n")
    finally:
        bus.shutdown()


if __name__ == "__main__":
    iface = sys.argv[1] if len(sys.argv) > 1 else "can1"
    analyze_dimming(iface)
