#!/usr/bin/env python3
"""
Helper script to analyze CAN messages and identify dimming level patterns.

Usage:
  python analyze_dimming.py can1

Instructions:
  1. Run this script while monitoring a CAN interface
  2. Adjust dimming levels on the physical switches
  3. Watch the output to identify which bytes change with dimming
  4. Once patterns are identified, update PATTERNS in canlistener.py

The script shows:
  - Full hex dump with byte indices for each message
  - Byte-by-byte diff when messages change
  - Correlation analysis to help identify dimming bytes
"""

import sys
import can
from collections import defaultdict

from canlistener import _prefix_lookup, _bloc9_id_from_low


def analyze_dimming(can_interface='can1'):
    """Listen and show detailed byte-level analysis for dimming identification."""
    
    last_seen = {}
    byte_changes = defaultdict(lambda: defaultdict(list))  # Track which bytes change per device
    
    bus = can.interface.Bus(channel=can_interface, interface='socketcan')
    try:
        print(f"Analyzing dimming on {can_interface}")
        print("Adjust dimming levels and watch for byte changes...\n")
        
        while True:
            msg = bus.recv(timeout=1.0)
            if msg is None:
                continue
            
            arb = msg.arbitration_id
            key, pattern = _prefix_lookup(arb)
            if pattern is None:
                continue
            
            low = arb & 0xFF
            bloc9_id = _bloc9_id_from_low(low)
            raw = bytes(msg.data)
            
            id_pair = (key, bloc9_id)
            prev = last_seen.get(id_pair)
            
            # Show hex dump with indices
            hex_dump = ' '.join(f"{i}:{b:02X}" for i, b in enumerate(raw))
            
            if prev is None:
                print(f"\n{pattern['name']} ID:{bloc9_id} [FIRST SEEN]")
                print(f"  HEX: {hex_dump}")
                last_seen[id_pair] = raw
                continue
            
            if prev != raw:
                print(f"\n{pattern['name']} ID:{bloc9_id} [CHANGED]")
                print(f"  HEX: {hex_dump}")
                
                # Show byte-by-byte diff
                diffs = []
                for i, (old_byte, new_byte) in enumerate(zip(prev, raw)):
                    if old_byte != new_byte:
                        diffs.append(f"byte[{i}]: 0x{old_byte:02X}→0x{new_byte:02X} ({old_byte}→{new_byte})")
                        byte_changes[id_pair][i].append((old_byte, new_byte))
                
                if diffs:
                    print("  DIFF: " + ", ".join(diffs))
                    
                    # Suggest potential dimming bytes (those that change frequently)
                    for byte_idx in sorted(set(i for i in range(len(raw)) if prev[i] != raw[i])):
                        changes = byte_changes[id_pair][byte_idx]
                        if len(changes) >= 2:
                            values = sorted(set(new for old, new in changes))
                            if len(values) > 2:  # More than just on/off
                                print(f"  → byte[{byte_idx}] might be dimming (values seen: {values})")
                
                last_seen[id_pair] = raw
                
    except KeyboardInterrupt:
        print("\n\nAnalysis Summary:")
        print("=" * 60)
        
        for id_pair, byte_dict in byte_changes.items():
            key, bloc9_id = id_pair
            print(f"\n{key} ID:{bloc9_id}:")
            
            for byte_idx in sorted(byte_dict.keys()):
                changes = byte_dict[byte_idx]
                unique_values = sorted(set(new for old, new in changes))
                print(f"  byte[{byte_idx}]: {len(changes)} changes, values: {unique_values}")
                
                # If many unique values, likely dimming
                if len(unique_values) > 2:
                    print(f"    ⚠ LIKELY DIMMING BYTE (range: {min(unique_values)}-{max(unique_values)})")
                    print(f"    Add to PATTERNS: 'sN_dim': {{'template': '[{byte_idx}]', 'type': 'byte', 'formatter': 'SN_DIM={{}}'}}") 
        
        print("\n")
    finally:
        bus.shutdown()


if __name__ == '__main__':
    iface = sys.argv[1] if len(sys.argv) > 1 else 'can1'
    analyze_dimming(iface)
