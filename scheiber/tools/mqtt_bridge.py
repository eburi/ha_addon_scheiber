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

# Import command functions from scheiber module
from scheiber import bloc9_switch

# Import device class system
from devices import create_device


def setup_logging(log_level="info"):
    """Configure logging to console with appropriate level."""
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    level = level_map.get(log_level.lower(), logging.INFO)
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
        mqtt_topic_prefix="homeassistant",
        log_level="info",
    ):
        self.logger = logging.getLogger(__name__)
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_password = mqtt_password
        self.can_interface = can_interface
        # Normalize topic prefix: strip trailing slash for consistent formatting
        self.mqtt_topic_prefix = mqtt_topic_prefix.rstrip("/")
        self.log_level = log_level

        self.can_bus = None
        self.mqtt_client = None
        self.last_seen = {}

        # Track device instances: (device_type, device_id) -> ScheiberCanDevice
        self.devices = {}

        # Bus statistics tracking
        self.bus_stats = {
            "unique_sender_ids": set(),
            "known_sender_ids": set(),
            "message_timestamps": [],  # For calculating messages per minute
            "total_messages": 0,
        }
        self.last_bus_stats_json = None  # Track last published state to detect changes

        self.logger.info(
            f"Initialized MQTTBridge with mqtt_host={mqtt_host}:{mqtt_port}, can_interface={can_interface}, topic_prefix={self.mqtt_topic_prefix}"
        )

    def on_mqtt_connect(self, client, userdata, flags, reason_code, properties):
        """Callback for MQTT connection (VERSION2)."""
        if reason_code == 0:
            self.logger.info("Connected to MQTT broker")
            # Subscribe to all command topics for device control
            command_topic = f"{self.mqtt_topic_prefix}/scheiber/+/+/+/set"
            client.subscribe(command_topic)
            self.logger.info(f"Subscribed to command topic: {command_topic}")
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
        """Callback for received MQTT messages - handle command topics."""
        topic = msg.topic
        payload = msg.payload.decode().strip()

        self.logger.debug(f"Received MQTT message on {topic}: {payload}")

        # Parse command topics: <prefix>/scheiber/<device_type>/<bus_id>/<property>/set
        if topic.endswith("/set"):
            self.handle_command(topic, payload)

    def handle_command(self, topic, payload):
        """Handle command messages for device control."""
        import re

        # Parse topic: <prefix>/scheiber/<device_type>/<bus_id>/<property>/set
        pattern = rf"^{re.escape(self.mqtt_topic_prefix)}/scheiber/([^/]+)/([^/]+)/([^/]+)/set$"
        match = re.match(pattern, topic)

        if not match:
            self.logger.warning(f"Could not parse command topic: {topic}")
            return

        device_type = match.group(1)
        bus_id_str = match.group(2)
        property_name = match.group(3)

        try:
            bus_id = int(bus_id_str)
        except ValueError:
            self.logger.error(f"Invalid bus_id '{bus_id_str}' in topic {topic}")
            return

        # Handle bloc9 switch commands
        if device_type == "bloc9":
            # Check if this is a brightness command
            if property_name == "brightness":
                # Brightness command format: <prefix>/scheiber/bloc9/<bus_id>/brightness/set
                # This is a global brightness for the device (not implemented yet)
                self.logger.warning(f"Global brightness command not supported: {topic}")
                return

            # Extract switch number and check for brightness suffix
            if property_name.startswith("s") and "_brightness" in property_name:
                # Individual switch brightness: s1_brightness, s2_brightness, etc.
                base_property = property_name.replace("_brightness", "")
                if base_property[1:].isdigit():
                    switch_nr = int(base_property[1:]) - 1  # s1=0, s2=1, etc.

                    try:
                        brightness = int(payload)
                        if brightness < 0 or brightness > 255:
                            self.logger.error(
                                f"Brightness value out of range (0-255): {brightness}"
                            )
                            return

                        self.logger.info(
                            f"Executing bloc9_switch: device={bus_id}, switch={switch_nr}, brightness={brightness}"
                        )

                        bloc9_switch(
                            self.can_interface,
                            bus_id,
                            switch_nr,
                            True,
                            brightness=brightness,
                        )
                        self.logger.info(
                            f"Brightness command sent successfully to {device_type} {bus_id} {property_name}"
                        )
                    except ValueError:
                        self.logger.error(f"Invalid brightness value: {payload}")
                    except Exception as e:
                        self.logger.error(f"Failed to send brightness command: {e}")
                else:
                    self.logger.warning(
                        f"Unknown property '{property_name}' for {device_type}"
                    )
            elif property_name.startswith("s") and property_name[1:].isdigit():
                # Simple ON/OFF command for switch
                switch_nr = int(property_name[1:]) - 1  # s1=0, s2=1, etc.

                # Parse payload: "1" or "ON" = True, "0" or "OFF" = False
                state = payload in ("1", "ON", "on", "true", "True")

                self.logger.info(
                    f"Executing bloc9_switch: device={bus_id}, switch={switch_nr}, state={state}"
                )

                try:
                    bloc9_switch(self.can_interface, bus_id, switch_nr, state)
                    self.logger.info(
                        f"Command sent successfully to {device_type} {bus_id} {property_name}"
                    )
                except Exception as e:
                    self.logger.error(f"Failed to send command: {e}")
            else:
                self.logger.warning(
                    f"Unknown property '{property_name}' for {device_type}"
                )
        else:
            self.logger.warning(f"Unsupported device type: {device_type}")

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

    def update_bus_statistics(self, arb_id, is_known_device):
        """Update bus statistics with a new message."""
        import time

        # Extract sender ID from arbitration ID (lowest byte)
        sender_id = arb_id & 0xFF

        # Update statistics
        self.bus_stats["unique_sender_ids"].add(sender_id)
        if is_known_device:
            self.bus_stats["known_sender_ids"].add(sender_id)

        # Track message timestamp for rate calculation
        current_time = time.time()
        self.bus_stats["message_timestamps"].append(current_time)
        self.bus_stats["total_messages"] += 1

        # Keep only last 60 seconds of timestamps for messages-per-minute calculation
        cutoff_time = current_time - 60
        self.bus_stats["message_timestamps"] = [
            ts for ts in self.bus_stats["message_timestamps"] if ts > cutoff_time
        ]

    def publish_bus_statistics(self):
        """Publish bus statistics to <prefix>/scheiber."""
        import time

        # Calculate messages per minute
        current_time = time.time()
        cutoff_time = current_time - 60
        recent_messages = [
            ts for ts in self.bus_stats["message_timestamps"] if ts > cutoff_time
        ]
        messages_per_minute = len(recent_messages)

        # Calculate bus load (messages per second)
        bus_load = messages_per_minute / 60.0

        topic = f"{self.mqtt_topic_prefix}/scheiber"
        payload = {
            "bus_load": round(bus_load, 2),
            "messages_per_minute": messages_per_minute,
            "total_messages": self.bus_stats["total_messages"],
            "unique_sender_ids": len(self.bus_stats["unique_sender_ids"]),
            "known_sender_ids": len(self.bus_stats["known_sender_ids"]),
            "unique_sender_id_list": sorted(list(self.bus_stats["unique_sender_ids"])),
            "known_sender_id_list": sorted(list(self.bus_stats["known_sender_ids"])),
        }

        payload_json = json.dumps(payload)

        # Only publish if changed
        if payload_json != self.last_bus_stats_json:
            self.logger.debug(f"Publishing bus stats to {topic}: {payload_json}")
            self.mqtt_client.publish(topic, payload_json, qos=1, retain=True)
            self.last_bus_stats_json = payload_json

    def decode_message(self, matcher, raw_data):
        """Decode properties from raw message data using matcher templates."""
        decoded = {}
        properties = matcher.get("properties", {})

        for prop_name, prop_config in properties.items():
            # Skip properties with no configuration (incomplete YAML)
            if prop_config is None:
                self.logger.warning(
                    f"Property '{prop_name}' has no configuration, skipping"
                )
                continue
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
            message_count = 0
            while True:
                msg = self.can_bus.recv(timeout=1.0)
                if msg is None:
                    continue

                arb = msg.arbitration_id
                device_key, device_config, matcher, bus_id = _find_device_and_matcher(
                    arb
                )

                # Update bus statistics for all messages (known or unknown)
                is_known = device_config is not None
                self.update_bus_statistics(arb, is_known)

                # Publish bus statistics every 10 messages or when new devices are seen
                message_count += 1
                if message_count % 10 == 0:
                    self.publish_bus_statistics()

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

                # Get or create device instance
                device_instance_key = (device_key, bus_id)

                if device_instance_key not in self.devices:
                    # First time seeing this device - create device instance
                    self.logger.info(
                        f"First message from {device_key} ID:{bus_id}, creating device instance"
                    )

                    device = create_device(
                        device_key,
                        bus_id,
                        device_config,
                        self.mqtt_client,
                        self.mqtt_topic_prefix,
                    )
                    self.devices[device_instance_key] = device

                    # Publish device info and discovery configs
                    device.publish_device_info()
                    device.publish_discovery_config()

                    # Publish initial bus statistics when first device is seen
                    self.publish_bus_statistics()

                    published_devices.add(device_instance_key)
                else:
                    device = self.devices[device_instance_key]

                # Update device state with new properties
                device.update_state(decoded)

                # Publish individual property states
                for prop_name, value in decoded.items():
                    device.publish_state(prop_name, value)

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
        default="homeassistant",
        help="MQTT topic prefix (default: homeassistant). Trailing slash will be stripped.",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level (default: info)",
    )

    args = parser.parse_args()

    logger = setup_logging(log_level=args.log_level)
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
        log_level=args.log_level,
    )
    bridge.run()


if __name__ == "__main__":
    main()
