#!/usr/bin/env python3
"""
List all CAN matchers registered by the Scheiber system.

This program loads scheiber-config.yaml, creates all devices,
and displays all matchers with their corresponding output names.
"""

import sys
import os

# Add scheiber module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scheiber", "src"))

import yaml
from unittest.mock import Mock
from scheiber.bloc9 import Bloc9Device


def load_config(config_path):
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def create_device_from_config(device_config, mock_bus):
    """Create a device from configuration."""
    device_type = device_config.get("type")
    bus_id = device_config.get("bus_id")
    name = device_config.get("name", f"{device_type}_{bus_id}")

    if device_type != "bloc9":
        print(f"Warning: Unknown device type '{device_type}'")
        return None

    # Extract lights and switches config
    lights_config = device_config.get("lights", {})
    switches_config = device_config.get("switches", {})

    # Create Bloc9Device
    device = Bloc9Device(
        device_id=bus_id,
        can_bus=mock_bus,
        lights_config=lights_config,
        switches_config=switches_config,
    )

    return device


def main():
    """Main program."""
    config_path = "scheiber-config.yaml"

    if not os.path.exists(config_path):
        print(f"Error: Config file '{config_path}' not found")
        sys.exit(1)

    print(f"Loading configuration from {config_path}...")
    config = load_config(config_path)

    if "devices" not in config:
        print("Error: No 'devices' section in config")
        sys.exit(1)

    print(f"Found {len(config['devices'])} devices\n")

    # Create mock CAN bus
    mock_bus = Mock()

    # Track all devices and matchers
    devices = []
    all_matchers = []

    # Create all devices
    for device_config in config["devices"]:
        device = create_device_from_config(device_config, mock_bus)
        if device:
            devices.append((device_config, device))

    print(f"Created {len(devices)} devices\n")
    print("=" * 80)
    print("MATCHER REGISTRATION REPORT")
    print("=" * 80)
    print()

    # List matchers for each device
    for device_config, device in devices:
        bus_id = device_config["bus_id"]
        device_name = device_config["name"]

        print(f"Device: {device_name} (bus_id={bus_id})")
        print(f"  Type: {device_config['type']}")
        print()

        # Get matchers
        matchers = device.get_matchers()

        # Separate by type
        switch_matchers = []
        light_matchers = []
        system_matchers = []

        for matcher in matchers:
            arb_id = matcher.pattern

            # Check if this is a switch change message
            if (arb_id & 0xFFFFFF00) in [0x02160600, 0x02180600, 0x021A0600]:
                # Get outputs for this matcher
                outputs = device._matcher_to_outputs.get(arb_id, [])
                for output in outputs:
                    if hasattr(output, "_brightness"):  # DimmableLight
                        light_matchers.append((matcher, output.name, output.switch_nr))
                    else:  # Switch
                        switch_matchers.append((matcher, output.name, output.switch_nr))
            # Heartbeat
            elif (arb_id & 0xFFFFFF00) == 0x00000600:
                system_matchers.append(
                    (matcher, "Heartbeat (low-priority status)", None)
                )
            # Command echo
            elif (arb_id & 0xFFFFFF00) == 0x02360600:
                system_matchers.append((matcher, "Command echo", None))

        # Print lights
        if light_matchers:
            print("  Lights:")
            # Sort by switch number
            light_matchers.sort(key=lambda x: x[2])
            current_matcher = None
            for matcher, name, switch_nr in light_matchers:
                if matcher != current_matcher:
                    print(
                        f"    Matcher: pattern=0x{matcher.pattern:08X}, mask=0x{matcher.mask:08X}"
                    )
                    current_matcher = matcher
                print(f"      → S{switch_nr+1}: {name}")
            print()

        # Print switches
        if switch_matchers:
            print("  Switches:")
            # Sort by switch number
            switch_matchers.sort(key=lambda x: x[2])
            current_matcher = None
            for matcher, name, switch_nr in switch_matchers:
                if matcher != current_matcher:
                    print(
                        f"    Matcher: pattern=0x{matcher.pattern:08X}, mask=0x{matcher.mask:08X}"
                    )
                    current_matcher = matcher
                print(f"      → S{switch_nr+1}: {name}")
            print()

        # Print system matchers
        if system_matchers:
            print("  System:")
            for matcher, description, _ in system_matchers:
                print(
                    f"    Matcher: pattern=0x{matcher.pattern:08X}, mask=0x{matcher.mask:08X}"
                )
                print(f"      → {description}")
            print()

        print("-" * 80)
        print()

    # Summary statistics
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()

    total_matchers = sum(len(device.get_matchers()) for _, device in devices)
    total_lights = sum(len(device.lights) for _, device in devices)
    total_switches = sum(len(device.switches) for _, device in devices)

    print(f"Total devices:  {len(devices)}")
    print(f"Total matchers: {total_matchers}")
    print(f"Total lights:   {total_lights}")
    print(f"Total switches: {total_switches}")
    print()

    # Show matcher pattern breakdown
    print("Matcher Pattern Distribution:")
    pattern_counts = {}
    for _, device in devices:
        for matcher in device.get_matchers():
            pattern_type = matcher.pattern & 0xFFFFFF00
            pattern_counts[pattern_type] = pattern_counts.get(pattern_type, 0) + 1

    pattern_names = {
        0x02160600: "S1/S2 state change",
        0x02180600: "S3/S4 state change",
        0x021A0600: "S5/S6 state change",
        0x00000600: "Heartbeat",
        0x02360600: "Command echo",
    }

    for pattern_type in sorted(pattern_counts.keys()):
        count = pattern_counts[pattern_type]
        name = pattern_names.get(pattern_type, f"Unknown (0x{pattern_type:08X})")
        print(f"  {name:30s} : {count:3d} matchers")

    print()


if __name__ == "__main__":
    main()
