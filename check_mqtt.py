#!/usr/bin/env python3
"""Check MQTT topics to verify discovery configs."""

import paho.mqtt.client as mqtt
import time
import json

messages = []


def on_message(client, userdata, message):
    messages.append((message.topic, message.payload.decode()))


# Connect to MQTT
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set("mqtt_user", "mqtt")
client.on_message = on_message

print("Connecting to MQTT broker...")
client.connect("192.168.55.222", 1883)
client.subscribe("homeassistant/#")

print("Listening for messages...")
client.loop_start()
time.sleep(3)
client.loop_stop()
client.disconnect()

print(f"\nFound {len(messages)} messages under homeassistant/#\n")

# Group by topic type
discovery_configs = []
state_topics = []
other_topics = []

for topic, payload in sorted(messages):
    if "/config" in topic:
        discovery_configs.append((topic, payload))
    elif "/state" in topic or "/brightness" in topic or "/availability" in topic:
        state_topics.append((topic, payload))
    else:
        other_topics.append((topic, payload))

print(f"Discovery configs: {len(discovery_configs)}")
print(f"State topics: {len(state_topics)}")
print(f"Other topics: {len(other_topics)}")

print("\n=== Discovery Config Topics (first 20) ===")
for topic, payload in discovery_configs[:20]:
    try:
        config = json.loads(payload)
        print(f"{topic}")
        print(f"  name: {config.get('name')}")
        print(f"  unique_id: {config.get('unique_id')}")
        print(f"  state_topic: {config.get('state_topic')}")
    except:
        print(f"{topic}: {payload[:80]}...")

if len(discovery_configs) > 20:
    print(f"\n... and {len(discovery_configs) - 20} more discovery configs")

print("\n=== Sample State Topics (first 10) ===")
for topic, payload in state_topics[:10]:
    print(f"{topic}: {payload}")

print("\n=== Other Topics ===")
for topic, payload in other_topics[:10]:
    print(f"{topic}: {payload[:100]}")
