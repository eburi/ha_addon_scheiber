#!/usr/bin/env python3
"""
Capture MQTT snapshot for version comparison.

Saves all discovery configs under homeassistant/ to a JSON file for comparison.
"""

import json
import time
from pathlib import Path

import paho.mqtt.client as mqtt
import yaml


def capture_mqtt_snapshot(
    mqtt_host, mqtt_port, mqtt_user, mqtt_password, output_file, duration=3
):
    """
    Capture all MQTT messages under homeassistant/ prefix.

    Args:
        mqtt_host: MQTT broker hostname
        mqtt_port: MQTT broker port
        mqtt_user: MQTT username
        mqtt_password: MQTT password
        output_file: Path to save snapshot JSON
        duration: How long to listen for messages (seconds)
    """
    captured_topics = {}

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"Connected to MQTT broker at {mqtt_host}:{mqtt_port}")
            # Subscribe to all homeassistant topics
            client.subscribe("homeassistant/#")
            print("Subscribed to homeassistant/#")
        else:
            print(f"Failed to connect: {reason_code}")

    def on_message(client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode("utf-8")

        # Store topic and payload
        captured_topics[topic] = payload

        # Parse JSON if possible
        try:
            parsed = json.loads(payload)
            print(f"📥 {topic}")
        except:
            print(f"📥 {topic} (non-JSON)")

    # Create MQTT client
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(mqtt_user, mqtt_password)
    client.on_connect = on_connect
    client.on_message = on_message

    # Connect and listen
    try:
        client.connect(mqtt_host, mqtt_port, 60)
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return {}
    client.loop_start()

    print(f"\nListening for {duration} seconds...")
    time.sleep(duration)

    client.loop_stop()
    client.disconnect()

    # Organize topics by type
    organized = {
        "lights": {},
        "switches": {},
        "other": {},
        "metadata": {
            "capture_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_topics": len(captured_topics),
        },
    }

    for topic, payload in sorted(captured_topics.items()):
        # Parse the topic structure
        parts = topic.split("/")

        if len(parts) >= 3:
            component = parts[1]  # light, switch, etc.
            entity_id = parts[2]
            topic_type = parts[3] if len(parts) > 3 else "unknown"

            if component == "light":
                if entity_id not in organized["lights"]:
                    organized["lights"][entity_id] = {}
                organized["lights"][entity_id][topic_type] = payload
            elif component == "switch":
                if entity_id not in organized["switches"]:
                    organized["switches"][entity_id] = {}
                organized["switches"][entity_id][topic_type] = payload
            else:
                organized["other"][topic] = payload
        else:
            organized["other"][topic] = payload

    # Save to file
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(organized, f, indent=2, sort_keys=True)

    print(f"\n✅ Captured {len(captured_topics)} topics")
    print(f"   - {len(organized['lights'])} lights")
    print(f"   - {len(organized['switches'])} switches")
    print(f"   - {len(organized['other'])} other topics")
    print(f"\n💾 Saved to: {output_path}")

    return organized


if __name__ == "__main__":
    # Load config to get MQTT broker details
    config_path = Path("./scheiber.yaml")
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
        mqtt_host = config.get("mqtt", {}).get("host", "192.168.55.222")
        mqtt_port = config.get("mqtt", {}).get("port", 1883)
        mqtt_user = config.get("mqtt", {}).get("user", "mqtt_user")
        mqtt_password = config.get("mqtt", {}).get("password", "mqtt")
    else:
        mqtt_host = "192.168.55.222"
        mqtt_port = 1883
        mqtt_user = "mqtt_user"
        mqtt_password = "mqtt"

    print("=" * 80)
    print("MQTT SNAPSHOT CAPTURE")
    print("=" * 80)
    print()

    # Get version identifier from user
    version = input("Enter version identifier (e.g., v5, v6, v5.7.1): ").strip()

    if not version:
        print("Error: Version identifier is required")
        sys.exit(1)

    output_file = f"mqtt_snapshot_{version.replace('/', '_')}.json"

    capture_mqtt_snapshot(
        mqtt_host, mqtt_port, mqtt_user, mqtt_password, output_file, duration=3
    )
