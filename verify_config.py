#!/usr/bin/env python3
"""Analyze scheiber.yaml and show what should be published to MQTT."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "scheiber" / "src"))

from config_loader import load_config

config_path = "./scheiber.yaml"
config = load_config(config_path)

if not config:
    print("Failed to load configuration")
    sys.exit(1)

print(f"Configuration Summary: {config.get_summary()}\n")

print("=" * 80)
print("EXPECTED MQTT DISCOVERY TOPICS")
print("=" * 80)

for bus_id in sorted(config.get_all_bloc9_ids()):
    device_configs = config.get_bloc9_configs(bus_id)
    device_name = device_configs[0].device_name if device_configs else f"Bloc9 {bus_id}"

    print(f"\n### Bloc9 {bus_id} - {device_name} ({len(device_configs)} entities) ###")

    for dc in device_configs:
        # Discovery topic (standard HA pattern)
        discovery_topic = f"homeassistant/{dc.component}/{dc.entity_id}/config"

        # State/command topics (scheiber namespace)
        state_topic = f"homeassistant/scheiber/bloc9/{bus_id}/{dc.output}/state"
        command_topic = f"homeassistant/scheiber/bloc9/{bus_id}/{dc.output}/set"
        availability_topic = (
            f"homeassistant/scheiber/bloc9/{bus_id}/{dc.output}/availability"
        )

        print(f"\n  {dc.component}.{dc.entity_id} (output={dc.output})")
        print(f"    Name: {dc.name}")
        print(f"    Discovery: {discovery_topic}")
        print(f"    State: {state_topic}")
        print(f"    Command: {command_topic}")
        print(f"    Availability: {availability_topic}")

        if dc.component == "light":
            brightness_state = (
                f"homeassistant/scheiber/bloc9/{bus_id}/{dc.output}/brightness"
            )
            brightness_cmd = (
                f"homeassistant/scheiber/bloc9/{bus_id}/{dc.output}/set_brightness"
            )
            print(f"    Brightness State: {brightness_state}")
            print(f"    Brightness Cmd: {brightness_cmd}")

print("\n" + "=" * 80)
print("TOTAL DISCOVERY TOPICS TO BE PUBLISHED")
print("=" * 80)

total_lights = sum(
    1
    for configs in [
        config.get_bloc9_configs(bus_id) for bus_id in config.get_all_bloc9_ids()
    ]
    for configs_list in [configs]
    for c in configs_list
    if c.component == "light"
)
total_switches = sum(
    1
    for configs in [
        config.get_bloc9_configs(bus_id) for bus_id in config.get_all_bloc9_ids()
    ]
    for configs_list in [configs]
    for c in configs_list
    if c.component == "switch"
)

print(f"Lights: {total_lights} discovery topics")
print(f"Switches: {total_switches} discovery topics")
print(f"Total: {total_lights + total_switches} discovery topics")
print("\nEach entity also has:")
print("  - 1 state topic")
print("  - 1 command topic")
print("  - 1 availability topic")
print("  - 2 brightness topics (lights only)")
