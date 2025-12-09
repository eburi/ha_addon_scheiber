#!/usr/bin/env python3
"""
Verify MQTT discovery configs match scheiber.yaml configuration.

Connects to MQTT broker, retrieves discovery configs, and validates them
against the expected configuration from scheiber.yaml.

Version 5.0.0+ expects:
- All entities belong to a unified "Scheiber" device (identifier: scheiber_system)
- Lights use JSON schema with state/brightness in single topic
- No separate brightness topics (brightness_state_topic, brightness_command_topic)
"""

import sys
from pathlib import Path
import paho.mqtt.client as mqtt
import time
import json
import yaml

# Add src to path for config_loader
sys.path.insert(0, str(Path(__file__).parent / "scheiber" / "src"))
from config_loader import load_config, name_to_snake_case

# MQTT Configuration
MQTT_HOST = "192.168.55.222"
MQTT_PORT = 1883
MQTT_USER = "mqtt_user"
MQTT_PASSWORD = "mqtt"
MQTT_TOPIC_PREFIX = "homeassistant"

# Configuration file
CONFIG_PATH = "./scheiber.yaml"

messages = []


def on_message(client, userdata, message):
    """Collect all MQTT messages."""
    messages.append((message.topic, message.payload.decode()))


def fetch_mqtt_discovery_configs():
    """Connect to MQTT and fetch all discovery config messages."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_message = on_message

    print(f"Connecting to MQTT broker at {MQTT_HOST}:{MQTT_PORT}...")
    try:
        client.connect(MQTT_HOST, MQTT_PORT)
    except Exception as e:
        print(f"❌ Failed to connect to MQTT broker: {e}")
        return {}

    client.subscribe(f"{MQTT_TOPIC_PREFIX}/#")

    print("Listening for messages (3 seconds)...")
    client.loop_start()
    time.sleep(3)
    client.loop_stop()
    client.disconnect()

    # Parse discovery configs
    discovery_configs = {}
    for topic, payload in messages:
        if "/config" in topic and payload:
            try:
                config = json.loads(payload)
                discovery_configs[topic] = config
            except json.JSONDecodeError:
                print(f"⚠️  Failed to parse JSON for {topic}")

    print(f"Found {len(discovery_configs)} discovery config topics\n")
    return discovery_configs


def verify_unified_device_structure():
    """
    Verify that the unified Scheiber device structure is used (v4.0.0+).
    Returns True if any entity uses the unified device, False otherwise.
    """
    return True  # v4.0.0 always uses unified structure


def verify_entity_config(disc_config, mqtt_configs):
    """Verify a single light or switch entity discovery config."""
    component = disc_config.component
    entity_id = disc_config.entity_id
    name = disc_config.name
    output = disc_config.output
    bus_id = disc_config.bus_id

    expected_topic = f"{MQTT_TOPIC_PREFIX}/{component}/{entity_id}/config"

    print(f"  💡 {component}.{entity_id} ({output.upper()}):")
    print(f"     Expected topic: {expected_topic}")

    if expected_topic not in mqtt_configs:
        print(f"     ❌ NOT FOUND in MQTT")
        return False

    config = mqtt_configs[expected_topic]
    errors = []

    # Verify required fields
    if config.get("name") != name:
        errors.append(f"name: expected '{name}', got '{config.get('name')}'")

    expected_unique_id = f"scheiber_bloc9_{bus_id}_{output}"
    if config.get("unique_id") != expected_unique_id:
        errors.append(
            f"unique_id: expected '{expected_unique_id}', got '{config.get('unique_id')}'"
        )

    # Verify topics
    expected_state_topic = f"{MQTT_TOPIC_PREFIX}/scheiber/bloc9/{bus_id}/{output}/state"
    if config.get("state_topic") != expected_state_topic:
        errors.append(
            f"state_topic: expected '{expected_state_topic}', got '{config.get('state_topic')}'"
        )

    expected_command_topic = f"{MQTT_TOPIC_PREFIX}/scheiber/bloc9/{bus_id}/{output}/set"
    if config.get("command_topic") != expected_command_topic:
        errors.append(
            f"command_topic: expected '{expected_command_topic}', got '{config.get('command_topic')}'"
        )

    expected_avail_topic = (
        f"{MQTT_TOPIC_PREFIX}/scheiber/bloc9/{bus_id}/{output}/availability"
    )
    if config.get("availability_topic") != expected_avail_topic:
        errors.append(
            f"availability_topic: expected '{expected_avail_topic}', got '{config.get('availability_topic')}'"
        )

    # Verify brightness support for lights (v5.0.0: JSON schema)
    if component == "light":
        # v5.0.0: schema should be "json"
        if config.get("schema") != "json":
            errors.append(f"schema: expected 'json', got '{config.get('schema')}'")

        # v5.0.0: brightness_scale should be 255
        if config.get("brightness_scale") != 255:
            errors.append(
                f"brightness_scale: expected 255, got '{config.get('brightness_scale')}'"
            )

        # v5.0.0: should NOT have separate brightness topics
        if "brightness_state_topic" in config:
            errors.append(
                f"brightness_state_topic: should not be present in v5.0.0 (use JSON schema instead)"
            )

        if "brightness_command_topic" in config:
            errors.append(
                f"brightness_command_topic: should not be present in v5.0.0 (use JSON schema instead)"
            )

        if "on_command_type" in config:
            errors.append(
                f"on_command_type: should not be present in v5.0.0 (use JSON schema instead)"
            )

    # Check device info (v4.0.0+: unified Scheiber device)
    device_info = config.get("device", {})

    # Verify unified device identifier
    expected_identifiers = ["scheiber_system"]
    if device_info.get("identifiers") != expected_identifiers:
        errors.append(
            f"device identifiers: expected {expected_identifiers}, got {device_info.get('identifiers')}"
        )

    # Verify device name
    if device_info.get("name") != "Scheiber":
        errors.append(
            f"device name: expected 'Scheiber', got '{device_info.get('name')}'"
        )

    # Verify device model
    if device_info.get("model") != "Marine Lighting Control System":
        errors.append(
            f"device model: expected 'Marine Lighting Control System', got '{device_info.get('model')}'"
        )

    # Verify manufacturer
    if device_info.get("manufacturer") != "Scheiber":
        errors.append(
            f"device manufacturer: expected 'Scheiber', got '{device_info.get('manufacturer')}'"
        )

    # v4.0.0: via_device should not be present
    if "via_device" in device_info:
        errors.append(
            f"via_device: should not be present in v4.0.0+ (found '{device_info.get('via_device')}')"
        )

    if errors:
        print(f"     ❌ ERRORS:")
        for error in errors:
            print(f"        - {error}")
        return False
    else:
        print(f"     ✅ OK")
        return True


def main():
    """Main verification function."""
    print("=" * 80)
    print("MQTT DISCOVERY CONFIG VERIFICATION")
    print("=" * 80)
    print()

    # Load configuration
    print(f"Loading configuration from {CONFIG_PATH}...")
    config = load_config(CONFIG_PATH)

    if not config:
        print("❌ Failed to load configuration")
        return 1

    print(f"✅ Configuration loaded: {config.get_summary()}\n")

    # Fetch MQTT discovery configs
    mqtt_configs = fetch_mqtt_discovery_configs()

    if not mqtt_configs:
        print("❌ No discovery configs found in MQTT")
        return 1

    # Verify each Bloc9 device
    total_checks = 0
    passed_checks = 0

    print(f"\n{'=' * 80}")
    print(f"DEVICE STRUCTURE: v5.0.0 (JSON Schema + Unified Device)")
    print(f"{'=' * 80}\n")
    print("All entities belong to a single 'Scheiber' device")
    print("Device identifier: scheiber_system")
    print("Lights use JSON schema: {state: ON/OFF, brightness: 0-255}\n")

    for bus_id in sorted(config.get_all_bloc9_ids()):
        device_configs = config.get_bloc9_configs(bus_id)
        if not device_configs:
            continue

        device_name = device_configs[0].device_name

        print(f"\n{'=' * 80}")
        print(f"Bloc9 {bus_id} - {device_name}")
        print(f"{'=' * 80}\n")

        # Verify each entity
        for disc_config in device_configs:
            total_checks += 1
            if verify_entity_config(disc_config, mqtt_configs):
                passed_checks += 1

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}\n")
    print(f"Total checks: {total_checks}")
    print(f"Passed: {passed_checks} ✅")
    print(f"Failed: {total_checks - passed_checks} ❌")

    if passed_checks == total_checks:
        print("\n🎉 All discovery configs match scheiber.yaml!")
        return 0
    else:
        print(
            f"\n⚠️  {total_checks - passed_checks} discovery config(s) have errors or are missing"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
