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
from canlistener import DEVICE_TYPES, _find_device_and_matcher, _bloc9_id_from_low, _extract_property_value


def setup_logging(debug=False):
    """Configure logging to console with appropriate level."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='[%(levelname)s] %(asctime)s - %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)


class MQTTBridge:
    def __init__(self, mqtt_host, mqtt_user, mqtt_password, can_interface, mqtt_topic_prefix='scheiber', debug=False):
        self.logger = logging.getLogger(__name__)
        self.mqtt_host = mqtt_host
        self.mqtt_user = mqtt_user
        self.mqtt_password = mqtt_password
        self.can_interface = can_interface
        # Normalize topic prefix: strip trailing slash for consistent formatting
        self.mqtt_topic_prefix = mqtt_topic_prefix.rstrip('/')
        self.debug = debug

        self.can_bus = None
        self.mqtt_client = None
        self.last_seen = {}
        self.device_states = defaultdict(dict)  # (device_type, bus_id) -> {prop: value}

        self.logger.info(f"Initialized MQTTBridge with mqtt_host={mqtt_host}, can_interface={can_interface}, topic_prefix={self.mqtt_topic_prefix}")

    def on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback for MQTT connection."""
        if rc == 0:
            self.logger.info("Connected to MQTT broker")
        else:
            self.logger.error(f"Failed to connect to MQTT broker, return code {rc}")

    def on_mqtt_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection."""
        if rc != 0:
            self.logger.warning(f"Unexpected disconnection from MQTT broker, return code {rc}")
        else:
            self.logger.info("Disconnected from MQTT broker")

    def on_mqtt_message(self, client, userdata, msg):
        """Callback for received MQTT messages (if subscribed)."""
        self.logger.debug(f"Received MQTT message on {msg.topic}: {msg.payload.decode()}")

    def connect_mqtt(self):
        """Connect to MQTT broker."""
        self.logger.debug(f"Connecting to MQTT broker at {self.mqtt_host}:1883")
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_client.on_message = self.on_mqtt_message

        self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)
        self.mqtt_client.connect(self.mqtt_host, 1883, keepalive=60)
        self.mqtt_client.loop_start()
        self.logger.info(f"MQTT client started (user={self.mqtt_user})")

    def connect_can(self):
        """Connect to CAN bus."""
        self.logger.debug(f"Opening CAN interface {self.can_interface}")
        self.can_bus = can.interface.Bus(
            channel=self.can_interface,
            interface='socketcan'
        )
        self.logger.info(f"CAN bus opened on {self.can_interface}")

    def publish_message(self, device, device_id, raw_data, decoded_properties):
        """Publish a message to MQTT."""
        topic = f"{self.mqtt_topic_prefix}/{device}/{device_id}"
        payload = {
            "raw": " ".join(f"{b:02X}" for b in raw_data),
            "properties": decoded_properties
        }
        payload_json = json.dumps(payload)
        self.logger.debug(f"Publishing to {topic}: {payload_json}")
        self.mqtt_client.publish(topic, payload_json, qos=1, retain=False)

    def decode_message(self, matcher, raw_data):
        """Decode properties from raw message data using matcher templates."""
        decoded = {}
        properties = matcher.get('properties', {})
        
        for prop_name, prop_config in properties.items():
            template = prop_config.get('template')
            value = _extract_property_value(raw_data, template)
            decoded[prop_name] = value if value is not None else None
        
        return decoded

    def run(self):
        """Main loop: listen on CAN and publish to MQTT."""
        self.connect_mqtt()
        self.connect_can()

        self.logger.info("Starting CAN listener loop (Ctrl+C to stop)")
        try:
            while True:
                msg = self.can_bus.recv(timeout=1.0)
                if msg is None:
                    continue

                arb = msg.arbitration_id
                device_key, device_config, matcher, bus_id = _find_device_and_matcher(arb)
                
                if device_config is None or matcher is None:
                    self.logger.debug(f"Ignoring unknown arbitration ID 0x{arb:08X}")
                    continue

                raw = bytes(msg.data)
                
                # Track per-matcher to detect raw message changes
                id_triple = (device_key, bus_id, matcher['name'])
                prev = self.last_seen.get(id_triple)
                if prev == raw:
                    self.logger.debug(f"Skipping unchanged message for {device_key} ID:{bus_id} [{matcher['name']}]")
                    continue

                self.last_seen[id_triple] = raw
                self.logger.debug(f"New message from {device_config['name']} ID:{bus_id} [{matcher['name']}]")

                # Decode properties from this matcher
                decoded = self.decode_message(matcher, raw)
                
                # Update device state
                device_instance = (device_key, bus_id)
                self.device_states[device_instance].update(decoded)
                
                # Publish current state for this device
                self.publish_message(device_key, bus_id, raw, self.device_states[device_instance])

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
        epilog=__doc__
    )
    parser.add_argument(
        '--mqtt-user',
        default='mqtt_user',
        help='MQTT username (default: mqtt_user)'
    )
    parser.add_argument(
        '--mqtt-password',
        default='mqtt',
        help='MQTT password (default: mqtt)'
    )
    parser.add_argument(
        '--mqtt-host',
        default='localhost',
        help='MQTT broker hostname (default: localhost)'
    )
    parser.add_argument(
        '--can-interface',
        default='can1',
        help='CAN interface name (default: can1)'
    )
    parser.add_argument(
        '--mqtt-topic-prefix',
        default='scheiber',
        help='MQTT topic prefix (default: scheiber). Trailing slash will be stripped.'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    logger = setup_logging(debug=args.debug)
    logger.info("Starting Scheiber MQTT Bridge")
    logger.info(f"Configuration: mqtt_host={args.mqtt_host}, mqtt_user={args.mqtt_user}, can_interface={args.can_interface}")

    bridge = MQTTBridge(
        mqtt_host=args.mqtt_host,
        mqtt_user=args.mqtt_user,
        mqtt_password=args.mqtt_password,
        can_interface=args.can_interface,
        mqtt_topic_prefix=args.mqtt_topic_prefix,
        debug=args.debug
    )
    bridge.run()


if __name__ == '__main__':
    main()
