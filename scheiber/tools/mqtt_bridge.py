#!/usr/bin/env python3
"""
MQTT bridge for Scheiber CAN devices.

Listens on a CAN interface and publishes decoded messages to MQTT.
Messages are published as JSON to /scheiber/<device>/<id>/.

Usage:
  python mqtt_bridge.py [--mqtt-user USER] [--mqtt-password PASS] \
                        [--mqtt-host HOST] [--can-interface IFACE]

Defaults:
  mqtt_user: mqtt_user
  mqtt_password: mqtt
  mqtt_host: localhost
  can_interface: can1
"""

import argparse
import json
import logging
import sys
from collections import defaultdict

import can
import paho.mqtt.client as mqtt

# Import device types and utilities from canlistener (relative import - run from tools/ folder)
from canlistener import (
    DEVICE_TYPES,
    _find_device_and_matcher,
    _bloc9_id_from_low,
    _extract_property_value,
)


def setup_logging(debug=False):
    """Configure logging to console with appropriate level."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(levelname)s] %(asctime)s - %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


class MQTTBridge:
    def __init__(
        self,
        mqtt_host,
        mqtt_user,
        mqtt_password,
        can_interface,
        mqtt_port=1883,
        mqtt_topic_prefix="scheiber",
        debug=False,
    ):
        self.logger = logging.getLogger(__name__)
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_password = mqtt_password
        self.can_interface = can_interface
        # Normalize topic prefix: strip trailing slash for consistent formatting
        self.mqtt_topic_prefix = mqtt_topic_prefix.rstrip("/")
        self.debug = debug

        self.can_bus = None
        self.mqtt_client = None
        self.last_seen = {}
        self.device_states = defaultdict(dict)  # (device_type, bus_id) -> {prop: value}

        self.logger.info(
            f"Initialized MQTTBridge with mqtt_host={mqtt_host}:{mqtt_port}, can_interface={can_interface}, topic_prefix={self.mqtt_topic_prefix}"
        )

    def on_mqtt_connect(self, client, userdata, flags, reason_code, properties):
        """Callback for MQTT connection (VERSION2)."""
        if reason_code == 0:
            self.logger.info("Connected to MQTT broker")
        else:
            self.logger.error(
                f"Failed to connect to MQTT broker, reason code {reason_code}"
            )

    def on_mqtt_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties
    ):
        """Callback for MQTT disconnection (VERSION2)."""
        if reason_code != 0:
            self.logger.warning(
                f"Unexpected disconnection from MQTT broker, reason code {reason_code}"
            )
        else:
            self.logger.info("Disconnected from MQTT broker")

    def on_mqtt_message(self, client, userdata, msg):
        """Callback for received MQTT messages (if subscribed)."""
        self.logger.debug(
            f"Received MQTT message on {msg.topic}: {msg.payload.decode()}"
        )

    def connect_mqtt(self):
        """Connect to MQTT broker."""
        self.logger.debug(
            f"Connecting to MQTT broker at {self.mqtt_host}:{self.mqtt_port}"
        )
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_client.on_message = self.on_mqtt_message

        self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)
        self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
        self.mqtt_client.loop_start()
        self.logger.info(f"MQTT client started (user={self.mqtt_user})")

    def connect_can(self):
        """Connect to CAN bus."""
        self.logger.debug(f"Opening CAN interface {self.can_interface}")
        self.can_bus = can.interface.Bus(
            channel=self.can_interface, interface="socketcan"
        )
        self.logger.info(f"CAN bus opened on {self.can_interface}")

    def publish_device_info(self, device_type, device_id, device_config):
        """Publish device information to <prefix>/scheiber/<device-type>/<bus-id>."""
        topic = f"{self.mqtt_topic_prefix}/scheiber/{device_type}/{device_id}"
        payload = {
            "name": device_config.get("name", device_type),
            "device_type": device_type,
            "bus_id": device_id,
        }
        payload_json = json.dumps(payload)
        self.logger.debug(f"Publishing device info to {topic}: {payload_json}")
        self.mqtt_client.publish(topic, payload_json, qos=1, retain=True)

    def publish_ha_discovery_config(
        self, device_type, device_id, device_config, property_name
    ):
        """Publish Home Assistant MQTT Discovery config for a light component."""
        # Discovery topic format: <discovery_prefix>/light/<device_type>_<bus_id>_<property>/config
        discovery_prefix = self.mqtt_topic_prefix
        unique_id = f"{device_type}_{device_id}_{property_name}"
        object_id = f"scheiber_{device_type}_{device_id}_{property_name}"

        config_topic = f"{discovery_prefix}/light/{unique_id}/config"
        state_topic = f"{self.mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{property_name}/state"

        config_payload = {
            "name": f"{device_config.get('name', device_type)} {device_id} {property_name.upper()}",
            "unique_id": unique_id,
            "object_id": object_id,
            "state_topic": state_topic,
            "command_topic": f"{self.mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{property_name}/set",
            "payload_on": "1",
            "payload_off": "0",
            "state_on": "1",
            "state_off": "0",
            "optimistic": False,
            "qos": 1,
            "retain": True,
            "device": {
                "identifiers": [f"scheiber_{device_type}_{device_id}"],
                "name": f"{device_config.get('name', device_type)} {device_id}",
                "model": device_config.get("name", device_type),
                "manufacturer": "Scheiber",
            },
        }

        # Add brightness support if dimming property exists
        dim_property = f"{property_name}_dim"
        # Check if dimming is configured in any matcher
        has_dimming = any(
            dim_property in matcher.get("properties", {})
            for matcher in device_config.get("matchers", [])
        )

        if has_dimming:
            config_payload["brightness_state_topic"] = (
                f"{self.mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{dim_property}/state"
            )
            config_payload["brightness_command_topic"] = (
                f"{self.mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{dim_property}/set"
            )
            config_payload["brightness_scale"] = 255

        config_json = json.dumps(config_payload)
        self.logger.debug(f"Publishing HA discovery config to {config_topic}")
        self.mqtt_client.publish(config_topic, config_json, qos=1, retain=True)

    def publish_property_state(self, device_type, device_id, property_name, value):
        """Publish individual property state to <prefix>/scheiber/<device-type>/<bus-id>/<property>/state."""
        topic = f"{self.mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{property_name}/state"
        payload = str(value) if value is not None else "?"
        self.logger.debug(f"Publishing property state to {topic}: {payload}")
        self.mqtt_client.publish(topic, payload, qos=1, retain=True)

    def publish_message(self, device, device_id, raw_data, decoded_properties):
        """Publish a message to MQTT (DEPRECATED - kept for compatibility)."""
        topic = f"{self.mqtt_topic_prefix}/{device}/{device_id}"
        payload = {
            "raw": " ".join(f"{b:02X}" for b in raw_data),
            "properties": decoded_properties,
        }
        payload_json = json.dumps(payload)
        self.logger.debug(f"Publishing to {topic}: {payload_json}")
        self.mqtt_client.publish(topic, payload_json, qos=1, retain=False)

    def decode_message(self, matcher, raw_data):
        """Decode properties from raw message data using matcher templates."""
        decoded = {}
        properties = matcher.get("properties", {})

        for prop_name, prop_config in properties.items():
            template = prop_config.get("template")
            value = _extract_property_value(raw_data, template)
            decoded[prop_name] = value if value is not None else None

        return decoded

    def run(self):
        """Main loop: listen on CAN and publish to MQTT."""
        self.connect_mqtt()
        self.connect_can()

        # Track which devices we've published discovery configs for
        published_devices = set()

        self.logger.info("Starting CAN listener loop (Ctrl+C to stop)")
        try:
            while True:
                msg = self.can_bus.recv(timeout=1.0)
                if msg is None:
                    continue

                arb = msg.arbitration_id
                device_key, device_config, matcher, bus_id = _find_device_and_matcher(
                    arb
                )

                if device_config is None or matcher is None:
                    self.logger.debug(f"Ignoring unknown arbitration ID 0x{arb:08X}")
                    continue

                raw = bytes(msg.data)

                # Track per-matcher to detect raw message changes
                id_triple = (device_key, bus_id, matcher["name"])
                prev = self.last_seen.get(id_triple)
                if prev == raw:
                    self.logger.debug(
                        f"Skipping unchanged message for {device_key} ID:{bus_id} [{matcher['name']}]"
                    )
                    continue

                self.last_seen[id_triple] = raw
                self.logger.debug(
                    f"New message from {device_config['name']} ID:{bus_id} [{matcher['name']}]"
                )

                # Decode properties from this matcher
                decoded = self.decode_message(matcher, raw)

                # Update device state
                device_instance = (device_key, bus_id)

                # First time we see this device, publish discovery configs
                if device_instance not in published_devices:
                    self.logger.info(
                        f"First message from {device_key} ID:{bus_id}, publishing discovery configs"
                    )
                    self.publish_device_info(device_key, bus_id, device_config)

                    # Collect all unique properties across all matchers for this device
                    all_properties = set()
                    for m in device_config.get("matchers", []):
                        all_properties.update(m.get("properties", {}).keys())

                    # Publish discovery config for each switch property (not dimming properties)
                    for prop_name in all_properties:
                        if not prop_name.endswith(
                            "_dim"
                        ):  # Only switches, not dimming values
                            self.publish_ha_discovery_config(
                                device_key, bus_id, device_config, prop_name
                            )

                    published_devices.add(device_instance)

                # Update device state with new properties
                self.device_states[device_instance].update(decoded)

                # Publish individual property states
                for prop_name, value in decoded.items():
                    self.publish_property_state(device_key, bus_id, prop_name, value)

        except KeyboardInterrupt:
            self.logger.info("Stopping (Ctrl+C received)")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        self.logger.debug("Cleaning up resources")
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.logger.info("MQTT client stopped")
        if self.can_bus:
            self.can_bus.shutdown()
            self.logger.info("CAN bus closed")


def main():
    parser = argparse.ArgumentParser(
        description="MQTT bridge for Scheiber CAN devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mqtt-user", default="mqtt_user", help="MQTT username (default: mqtt_user)"
    )
    parser.add_argument(
        "--mqtt-password", default="mqtt", help="MQTT password (default: mqtt)"
    )
    parser.add_argument(
        "--mqtt-host",
        default="localhost",
        help="MQTT broker hostname (default: localhost)",
    )
    parser.add_argument(
        "--mqtt-port", type=int, default=1883, help="MQTT broker port (default: 1883)"
    )
    parser.add_argument(
        "--can-interface", default="can1", help="CAN interface name (default: can1)"
    )
    parser.add_argument(
        "--mqtt-topic-prefix",
        default="scheiber",
        help="MQTT topic prefix (default: scheiber). Trailing slash will be stripped.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    logger = setup_logging(debug=args.debug)
    logger.info("Starting Scheiber MQTT Bridge")
    logger.info(
        f"Configuration: mqtt_host={args.mqtt_host}:{args.mqtt_port}, mqtt_user={args.mqtt_user}, can_interface={args.can_interface}"
    )

    bridge = MQTTBridge(
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        mqtt_user=args.mqtt_user,
        mqtt_password=args.mqtt_password,
        can_interface=args.can_interface,
        mqtt_topic_prefix=args.mqtt_topic_prefix,
        debug=args.debug,
    )
    bridge.run()


if __name__ == "__main__":
    main()
