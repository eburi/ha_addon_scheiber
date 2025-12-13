#!/usr/bin/env python3
"""
Test debug logging for status message routing.

Demonstrates the new debug logging when outputs receive matched CAN messages.
"""

import sys
import os
import logging

# Add scheiber module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scheiber", "src"))

from unittest.mock import Mock
import can
from scheiber.bloc9 import Bloc9Device

# Set up logging to see debug messages
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    """Test debug logging when processing CAN messages."""
    print("=" * 80)
    print("Testing Debug Logging for Status Message Routing")
    print("=" * 80)
    print()

    mock_bus = Mock()

    # Create device with multiple outputs
    device = Bloc9Device(
        device_id=7,
        can_bus=mock_bus,
        lights_config={
            "s1": {"name": "Saloon Front Light"},
            "s2": {"name": "Saloon Aft Light"},
            "s5": {"name": "Cockpit Light"},
        },
        switches_config={
            "s6": {"name": "Fan Port"},
        },
    )

    print("Created Bloc9 device 7 with:")
    print("  - S1: Saloon Front Light (DimmableLight)")
    print("  - S2: Saloon Aft Light (DimmableLight)")
    print("  - S5: Cockpit Light (DimmableLight)")
    print("  - S6: Fan Port (Switch)")
    print()
    print("-" * 80)
    print()

    # Test 1: S1/S2 message
    print("TEST 1: Send S1/S2 message (0x021606B8)")
    print("  Expected: S1 and S2 should log receiving the message")
    print()

    msg_s1_s2 = can.Message(
        arbitration_id=0x021606B8,
        data=bytes(
            [0x80, 0x00, 0x11, 0x01, 0xC8, 0x00, 0x11, 0x01]
        ),  # S1: brightness=128 ON, S2: brightness=200 ON
        is_extended_id=True,
    )
    device.process_message(msg_s1_s2)
    print()
    print("-" * 80)
    print()

    # Test 2: S5/S6 message
    print("TEST 2: Send S5/S6 message (0x021A06B8)")
    print("  Expected: S5 (light) and S6 (switch) should log receiving the message")
    print()

    msg_s5_s6 = can.Message(
        arbitration_id=0x021A06B8,
        data=bytes(
            [0xFF, 0x00, 0x11, 0x01, 0x00, 0x00, 0x00, 0x01]
        ),  # S5: brightness=255 ON, S6: OFF but state bit ON
        is_extended_id=True,
    )
    device.process_message(msg_s5_s6)
    print()
    print("-" * 80)
    print()

    # Test 3: Heartbeat (device-level, no output logging)
    print("TEST 3: Send heartbeat message (0x000006B8)")
    print("  Expected: No output logging (heartbeat is device-level)")
    print()

    heartbeat = can.Message(
        arbitration_id=0x000006B8,
        data=bytes([0xFF] * 8),
        is_extended_id=True,
    )
    device.process_message(heartbeat)
    print()
    print("-" * 80)
    print()

    # Test 4: Wrong device message (should not log)
    print("TEST 4: Send message for device 8 (0x021606C0)")
    print("  Expected: No logging (message not for this device)")
    print()

    msg_device_8 = can.Message(
        arbitration_id=0x021606C0,  # Device 8, not device 7
        data=bytes([0x64, 0x00, 0x11, 0x01, 0x00, 0x00, 0x00, 0x00]),
        is_extended_id=True,
    )
    device.process_message(msg_device_8)
    print()
    print("=" * 80)
    print("Test Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()
