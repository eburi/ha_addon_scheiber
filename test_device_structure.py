#!/usr/bin/env python3
"""Test the new device structure to see what topics would be published."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "scheiber" / "src"))

from config_loader import load_config, name_to_snake_case

config_path = "./scheiber.yaml"
config = load_config(config_path)

if not config:
    print("Failed to load configuration")
    sys.exit(1)

print("=" * 80)
print("NEW HOME ASSISTANT DEVICE STRUCTURE")
print("=" * 80)

for bus_id in sorted(config.get_all_bloc9_ids()):
    device_configs = config.get_bloc9_configs(bus_id)
    if not device_configs:
        continue

    device_name = device_configs[0].device_name
    sensor_entity_id = name_to_snake_case(device_name)

    print(f"\n### Bloc9 {bus_id} - {device_name} ###")
    print(f"\n  1. BLOC9 SENSOR DEVICE:")
    print(f"     Discovery: homeassistant/sensor/{sensor_entity_id}/config")
    print(f"     State: homeassistant/scheiber/bloc9/{bus_id}")
    print(f"     Availability: homeassistant/scheiber/bloc9/{bus_id}/availability")
    print(f"     Device ID: scheiber_bloc9_{bus_id}")
    print(f"     Shows: bus_id and switches as JSON attributes")

    print(f"\n  2. INDIVIDUAL LIGHT/SWITCH DEVICES ({len(device_configs)} entities):")

    for dc in device_configs:
        discovery_topic = f"homeassistant/{dc.component}/{dc.entity_id}/config"
        state_topic = f"homeassistant/scheiber/bloc9/{bus_id}/{dc.output}/state"
        availability_topic = (
            f"homeassistant/scheiber/bloc9/{bus_id}/{dc.output}/availability"
        )

        print(f"\n     {dc.component}.{dc.entity_id} ({dc.output.upper()}):")
        print(f"       Name: {dc.name}")
        print(f"       Discovery: {discovery_topic}")
        print(f"       Device ID: scheiber_bloc9_{bus_id}_{dc.output}")
        print(f"       Via Device: scheiber_bloc9_{bus_id} (links to Bloc9 sensor)")
        print(f"       State: {state_topic}")
        print(f"       Availability: {availability_topic}")

        if dc.component == "light":
            print(
                f"       Brightness State: homeassistant/scheiber/bloc9/{bus_id}/{dc.output}/brightness"
            )
            print(
                f"       Brightness Cmd: homeassistant/scheiber/bloc9/{bus_id}/{dc.output}/set_brightness"
            )

print("\n" + "=" * 80)
print("DEVICE HIERARCHY")
print("=" * 80)
print("\nEach Bloc9 creates a device hierarchy in Home Assistant:")
print("  - Bloc9 sensor device (shows bus statistics)")
print("    └── Individual light devices (via_device → Bloc9)")
print("    └── Individual switch devices (via_device → Bloc9)")
print("\nThis creates a clear visual hierarchy in the HA devices page.")
