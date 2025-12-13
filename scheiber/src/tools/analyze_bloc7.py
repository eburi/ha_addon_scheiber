import argparse
import json
import logging
import threading
import time
from collections import defaultdict, deque

import can
import paho.mqtt.client as mqtt

# --- Configuration ---
MQTT_TOPICS = {
    "freshWater_0": "N/signalk/256004128/vessels/self/tanks/freshWater/0/currentLevel",
    "freshWater_1": "N/signalk/256004128/vessels/self/tanks/freshWater/1/currentLevel",
    "fuel_0": "N/signalk/256004128/vessels/self/tanks/fuel/0/currentLevel",
    "fuel_1": "N/signalk/256004128/vessels/self/tanks/fuel/1/currentLevel",
    "battery_5_voltage": "N/signalk/256004128/vessels/self/electrical/batteries/5/voltage",
    "battery_2_voltage": "N/signalk/256004128/vessels/self/electrical/batteries/2/voltage",
    "battery_6_voltage": "N/signalk/256004128/vessels/self/electrical/batteries/6/voltage",
}

# --- Global State ---
latest_mqtt_values = defaultdict(lambda: None)
can_message_history = defaultdict(
    lambda: {"timestamps": deque(maxlen=10), "data": deque(maxlen=10)}
)
running = True

# --- Logging ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def on_connect(client, userdata, flags, rc):
    """Callback for when the client receives a CONNACK response from the server."""
    if rc == 0:
        logging.info("Connected to MQTT Broker!")
        for topic in MQTT_TOPICS.values():
            client.subscribe(topic)
            logging.info(f"Subscribed to {topic}")
    else:
        logging.error(f"Failed to connect, return code {rc}\n")


def on_message(client, userdata, msg):
    """Callback for when a PUBLISH message is received from the server."""
    try:
        payload = json.loads(msg.payload.decode())
        value = payload.get("value")

        for name, topic in MQTT_TOPICS.items():
            if msg.topic == topic:
                if latest_mqtt_values[name] != value:
                    logging.info(f"MQTT Update: {name} = {value}")
                    latest_mqtt_values[name] = value
                break
    except (json.JSONDecodeError, AttributeError):
        logging.warning(f"Could not decode MQTT message on topic {msg.topic}")


def mqtt_listener(host, port, user, password):
    """Connects to MQTT and listens for topics."""
    client = mqtt.Client()
    client.username_pw_set(user, password)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, 60)
    client.loop_forever()


def can_listener(interface):
    """Listens for CAN messages and records their history."""
    global running
    try:
        with can.interface.Bus(channel=interface, bustype="socketcan") as bus:
            logging.info(f"Listening for CAN messages on {interface}...")
            for msg in bus:
                if not running:
                    break
                history = can_message_history[msg.arbitration_id]
                history["timestamps"].append(msg.timestamp)
                history["data"].append(msg.data)
    except Exception as e:
        logging.error(f"CAN bus error: {e}")
        running = False


def analyze_data():
    """Periodically analyzes the collected data for correlations."""
    last_analysis_time = time.time()
    while running:
        time.sleep(5)  # Analysis interval
        logging.info("--- Analyzing Data ---")

        # Check for regular CAN updates
        for can_id, history in list(can_message_history.items()):
            if len(history["timestamps"]) > 5:
                intervals = [
                    j - i
                    for i, j in zip(
                        history["timestamps"], list(history["timestamps"])[1:]
                    )
                ]
                avg_interval = sum(intervals) / len(intervals) if intervals else 0

                # Only consider messages that update somewhat regularly (e.g., every 0.5-10s)
                if 0.5 < avg_interval < 10:
                    last_data = history["data"][-1] if history["data"] else None
                    if last_data:
                        logging.info(
                            f"Regular CAN ID: {hex(can_id)} (avg interval: {avg_interval:.2f}s) | Data: {last_data.hex(' ')}"
                        )

                        # Correlation logic
                        for name, mqtt_val in latest_mqtt_values.items():
                            if mqtt_val is None:
                                continue

                            # Simple correlation: scale MQTT value and check if it matches a byte
                            # Tank levels are 0-1.0, scale to 0-255
                            if "freshWater" in name or "fuel" in name:
                                scaled_mqtt_val = int(mqtt_val * 255)
                                for i, byte_val in enumerate(last_data):
                                    if (
                                        abs(byte_val - scaled_mqtt_val) < 2
                                    ):  # Allow small tolerance
                                        print(
                                            f"  => POTENTIAL MATCH! CAN ID {hex(can_id)} byte[{i}] ({byte_val}) looks like {name} ({scaled_mqtt_val})"
                                        )

                            # Voltage is in Volts, maybe scaled by 10 or 100
                            elif "voltage" in name:
                                for scale in [10, 100]:
                                    scaled_mqtt_val = int(mqtt_val * scale)
                                    # Check single bytes
                                    for i, byte_val in enumerate(last_data):
                                        if abs(byte_val - scaled_mqtt_val) < 2:
                                            print(
                                                f"  => POTENTIAL MATCH! CAN ID {hex(can_id)} byte[{i}] ({byte_val}) looks like {name} * {scale} ({scaled_mqtt_val})"
                                            )
                                    # Check two bytes (little-endian)
                                    if len(last_data) > 1:
                                        for i in range(len(last_data) - 1):
                                            two_byte_val = last_data[i] + (
                                                last_data[i + 1] << 8
                                            )
                                            if abs(two_byte_val - scaled_mqtt_val) < 5:
                                                print(
                                                    f"  => POTENTIAL MATCH! CAN ID {hex(can_id)} bytes[{i}:{i+2}] ({two_byte_val}) looks like {name} * {scale} ({scaled_mqtt_val})"
                                                )


def main():
    parser = argparse.ArgumentParser(
        description="Analyze CAN bus traffic to identify Bloc7 messages."
    )
    parser.add_argument(
        "--can-interface", type=str, default="can1", help="CAN interface name."
    )
    parser.add_argument(
        "--mqtt-host", type=str, default="localhost", help="MQTT broker host."
    )
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port.")
    parser.add_argument(
        "--mqtt-user", type=str, default="mqtt_user", help="MQTT username."
    )
    parser.add_argument(
        "--mqtt-password", type=str, default="mqtt", help="MQTT password."
    )
    args = parser.parse_args()

    # Start MQTT listener in a background thread
    mqtt_thread = threading.Thread(
        target=mqtt_listener,
        args=(args.mqtt_host, args.mqtt_port, args.mqtt_user, args.mqtt_password),
        daemon=True,
    )
    mqtt_thread.start()

    # Start CAN listener in a background thread
    can_thread = threading.Thread(
        target=can_listener, args=(args.can_interface,), daemon=True
    )
    can_thread.start()

    # Start analysis in the main thread
    try:
        analyze_data()
    except KeyboardInterrupt:
        logging.info("Stopping analysis...")
        global running
        running = False
        time.sleep(1)


if __name__ == "__main__":
    main()
