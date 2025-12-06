#!/usr/bin/env python3
"""
Device class hierarchy for Scheiber CAN devices.

Base class ScheiberCanDevice provides common functionality.
Subclasses (Bloc9, etc.) add device-specific behavior including command handling.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import can


class ScheiberCanDevice(ABC):
    """Base class for all Scheiber CAN devices."""

    def __init__(
        self,
        device_type: str,
        device_id: int,
        device_config: Dict[str, Any],
        mqtt_client,
        mqtt_topic_prefix: str,
        can_bus: Optional[can.BusABC],
        data_dir: Optional[str] = None,
    ):
        self.device_type = device_type
        self.device_id = device_id
        self.device_config = device_config
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.can_bus = can_bus
        self.data_dir = data_dir
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}.{device_type}_{device_id}"
        )

        # Track device state: {property_name: value}
        self.state = {}

        # Track which properties have been published
        self.published_properties = set()

        # Track which properties are available (received data from CAN bus)
        self.available_properties = set()

    def get_base_topic(self) -> str:
        """Get the base MQTT topic for this device."""
        return f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}"

    def get_property_topic(self, property_name: str, suffix: str = "") -> str:
        """Get the MQTT topic for a specific property."""
        topic = f"{self.get_base_topic()}/{property_name}"
        if suffix:
            topic = f"{topic}/{suffix}"
        return topic

    def get_all_properties(self) -> Set[str]:
        """Get all unique properties across all matchers for this device."""
        all_properties = set()
        for matcher in self.device_config.get("matchers", []):
            all_properties.update(matcher.get("properties", {}).keys())
        return all_properties

    def update_state(self, decoded_properties: Dict[str, Any]):
        """Update device state with decoded properties."""
        self.state.update(decoded_properties)

    def mark_property_available(self, property_name: str):
        """Mark a property as available and publish availability status."""
        if property_name not in self.available_properties:
            self.available_properties.add(property_name)
            availability_topic = self.get_property_topic(property_name, "availability")
            self.logger.debug(
                f"Publishing availability to {availability_topic}: online"
            )
            self.mqtt_client.publish(availability_topic, "online", qos=1, retain=True)

    def register_command_topics(self) -> List[Tuple[str, Callable[[str, str], None]]]:
        """
        Register MQTT command topics this device wants to handle.

        Returns:
            List of (topic_pattern, handler_function) tuples.
            Topic patterns can include '+' wildcards for MQTT subscription.
        """
        return []

    def handle_command(self, topic: str, payload: str):
        """
        Handle a command received on an MQTT topic.

        Args:
            topic: Full MQTT topic where command was received
            payload: Command payload string
        """
        self.logger.warning(f"Unhandled command on {topic}: {payload}")

    @abstractmethod
    def publish_discovery_config(self):
        """Publish Home Assistant MQTT Discovery configuration."""
        pass

    @abstractmethod
    def publish_state(self, property_name: str, value: Any):
        """Publish property state to MQTT."""
        pass

    def publish_device_info(self):
        """Publish device information to MQTT."""
        topic = self.get_base_topic()
        payload = {
            "name": self.device_config.get("name", self.device_type),
            "device_type": self.device_type,
            "bus_id": self.device_id,
        }
        import json

        payload_json = json.dumps(payload)
        self.logger.debug(f"Publishing device info to {topic}: {payload_json}")
        self.mqtt_client.publish(topic, payload_json, qos=1, retain=True)


class Bloc9(ScheiberCanDevice):
    """Bloc9 device with switch and brightness support."""

    def __init__(
        self,
        device_type: str,
        device_id: int,
        device_config: Dict[str, Any],
        mqtt_client,
        mqtt_topic_prefix: str,
        can_bus: Optional[can.BusABC],
        data_dir: Optional[str] = None,
    ):
        super().__init__(
            device_type,
            device_id,
            device_config,
            mqtt_client,
            mqtt_topic_prefix,
            can_bus,
            data_dir,
        )

        # Set state cache directory from data_dir or use default
        if data_dir:
            self.state_cache_dir = Path(data_dir) / "state_cache"
        else:
            self.state_cache_dir = Path(__file__).parent / ".state_cache"

        self.logger.info(
            f"Initialized Bloc9 device: {device_type} {device_id}, state_cache={self.state_cache_dir}"
        )

        # Load persisted state and publish if available
        self._load_and_publish_persisted_state()

    def register_command_topics(self) -> List[Tuple[str, Callable[[str, str], None]]]:
        """Register command topics for all switch properties."""
        topics = []
        all_properties = self.get_all_properties()

        for prop_name in all_properties:
            # Skip internal properties
            if prop_name.endswith("_brightness") or prop_name.startswith("stat"):
                continue

            # Register ON/OFF command topic
            command_topic = self.get_property_topic(prop_name, "set")
            topics.append((command_topic, self.handle_command))

            # Register brightness command topic if brightness is supported
            if f"{prop_name}_brightness" in all_properties:
                brightness_topic = self.get_property_topic(prop_name, "set_brightness")
                topics.append((brightness_topic, self.handle_command))

        return topics

    def handle_command(self, topic: str, payload: str):
        """Handle ON/OFF and brightness commands for Bloc9 switches."""
        # Parse the topic to extract property name and command type
        # Topic format: <prefix>/scheiber/<device_type>/<device_id>/<property>/set[_brightness]
        topic_parts = topic.split("/")

        if len(topic_parts) < 2:
            self.logger.error(f"Invalid topic format: {topic}")
            return

        command_type = topic_parts[-1]  # 'set' or 'set_brightness'
        property_name = topic_parts[-2]  # e.g., 's1', 's2'

        # Validate property starts with 's' and has a digit
        if not (
            property_name.startswith("s")
            and len(property_name) >= 2
            and property_name[1:].isdigit()
        ):
            self.logger.warning(f"Invalid property name: {property_name}")
            return

        # Extract switch number (s1=0, s2=1, etc.)
        switch_nr = int(property_name[1:]) - 1

        try:
            if command_type == "set_brightness":
                # Handle brightness command
                brightness = int(payload)
                if brightness < 0 or brightness > 255:
                    self.logger.error(
                        f"Brightness value out of range (0-255): {brightness}"
                    )
                    return

                self.logger.info(
                    f"Executing brightness command: switch={switch_nr}, brightness={brightness}"
                )
                self._send_switch_command(switch_nr, True, brightness=brightness)

            elif command_type == "set":
                # Handle ON/OFF command
                state = payload in ("1", "ON", "on", "true", "True")
                self.logger.info(
                    f"Executing switch command: switch={switch_nr}, state={state}"
                )
                self._send_switch_command(switch_nr, state)
            else:
                self.logger.warning(f"Unknown command type: {command_type}")

        except ValueError as e:
            self.logger.error(f"Invalid command payload: {payload} - {e}")
        except Exception as e:
            self.logger.error(f"Failed to execute command: {e}")

    def _send_switch_command(
        self, switch_nr: int, state: bool, brightness: Optional[int] = None
    ):
        """
        Send a switch command to the Bloc9 device via CAN bus.

        Args:
            switch_nr: Switch number (0-5 for S1-S6)
            state: Boolean state (True for ON, False for OFF)
            brightness: Optional brightness level (0-255)
        """
        if not self.can_bus:
            self.logger.error("No CAN bus available for sending commands")
            return

        try:
            # Construct CAN ID: lowest byte = (bloc9_id << 3) | 0x80
            low_byte = ((self.device_id << 3) | 0x80) & 0xFF
            can_id = 0x02360600 | low_byte

            # Construct 4-byte body based on brightness parameter
            if brightness is not None:
                if brightness == 0:
                    # Brightness 0 = turn off
                    data = bytes([switch_nr, 0x00, 0x00, 0x00])
                    self.logger.debug(f"Switch {switch_nr} -> OFF (brightness=0)")
                elif brightness == 255:
                    # Brightness 255 = turn on (without brightness control)
                    data = bytes([switch_nr, 0x01, 0x00, 0x00])
                    self.logger.debug(f"Switch {switch_nr} -> ON (brightness=255)")
                else:
                    # Set brightness level (byte 1 = 0x11, byte 3 = brightness)
                    brightness_byte = max(1, min(254, brightness))
                    data = bytes([switch_nr, 0x11, 0x00, brightness_byte])
                    self.logger.debug(
                        f"Switch {switch_nr} -> brightness={brightness_byte}"
                    )
            else:
                # Simple ON/OFF mode
                state_byte = 0x01 if state else 0x00
                data = bytes([switch_nr, state_byte, 0x00, 0x00])
                self.logger.debug(f"Switch {switch_nr} -> {'ON' if state else 'OFF'}")

            # Send the message
            msg = can.Message(arbitration_id=can_id, data=data)
            self.can_bus.send(msg)
            self.logger.info(
                f"CAN TX: ID=0x{can_id:08X} Data={' '.join(f'{b:02X}' for b in data)}"
            )
        except Exception as e:
            self.logger.error(f"Failed to send CAN message: {e}")
            raise

    def publish_discovery_config(self):
        """Publish Home Assistant MQTT Discovery config for light components."""
        import json

        all_properties = self.get_all_properties()

        # Publish config for each switch property (not brightness/stat properties)
        for prop_name in all_properties:
            # Skip internal properties
            if prop_name.endswith("_brightness") or prop_name.startswith("stat"):
                continue

            unique_id = f"{self.device_type}_{self.device_id}_{prop_name}"
            default_entity_id = (
                f"light.scheiber_{self.device_type}_{self.device_id}_{prop_name}"
            )

            config_topic = self.get_property_topic(prop_name, "config")
            state_topic = self.get_property_topic(prop_name, "state")
            availability_topic = self.get_property_topic(prop_name, "availability")

            config_payload = {
                "name": f"{self.device_config.get('name', self.device_type)} {self.device_id} {prop_name.upper()}",
                "unique_id": unique_id,
                "default_entity_id": default_entity_id,
                "device_class": "light",
                "state_topic": state_topic,
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "command_topic": self.get_property_topic(prop_name, "set"),
                "payload_on": "1",
                "payload_off": "0",
                "state_on": "1",
                "state_off": "0",
                "optimistic": False,
                "qos": 1,
                "retain": True,
                "device": {
                    "identifiers": [f"scheiber_{self.device_type}_{self.device_id}"],
                    "name": f"{self.device_config.get('name', self.device_type)} {self.device_id}",
                    "model": self.device_config.get("name", self.device_type),
                    "manufacturer": "Scheiber",
                },
            }

            # Add brightness support if _brightness property exists
            if f"{prop_name}_brightness" in all_properties:
                config_payload["brightness"] = True
                config_payload["supported_color_modes"] = ["brightness"]
                config_payload["brightness_state_topic"] = self.get_property_topic(
                    prop_name, "brightness"
                )
                config_payload["brightness_command_topic"] = self.get_property_topic(
                    prop_name, "set_brightness"
                )

                # Publish initial brightness value
                brightness_topic = self.get_property_topic(prop_name, "brightness")
                self.logger.debug(
                    f"Publishing initial brightness to {brightness_topic}: ?"
                )
                self.mqtt_client.publish(brightness_topic, "?", qos=1, retain=True)

            config_json = json.dumps(config_payload)
            self.logger.debug(
                f"Publishing HA discovery config to {config_topic}: {config_json}"
            )
            self.mqtt_client.publish(config_topic, config_json, qos=1, retain=True)

            # Publish initial offline availability status
            self.logger.debug(
                f"Publishing initial availability to {availability_topic}: offline"
            )
            self.mqtt_client.publish(availability_topic, "offline", qos=1, retain=True)

            self.published_properties.add(prop_name)

    def publish_state(self, property_name: str, value: Any):
        """Publish property state to MQTT, handling brightness separately."""
        # Handle brightness properties
        if property_name.endswith("_brightness"):
            base_prop = property_name.replace("_brightness", "")

            # Mark base property as available when we get brightness data
            self.mark_property_available(base_prop)

            brightness_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{base_prop}/brightness"
            payload = str(value) if value is not None else "?"
            self.logger.debug(f"Publishing brightness to {brightness_topic}: {payload}")
            self.mqtt_client.publish(brightness_topic, payload, qos=1, retain=True)

            # Persist brightness state
            self._persist_state(property_name, value)
        # Skip stat properties
        elif property_name.startswith("stat"):
            return
        # Handle regular switch state
        else:
            # Mark property as available when we publish state
            self.mark_property_available(property_name)

            topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{property_name}/state"
            payload = str(value) if value is not None else "?"
            self.logger.debug(f"Publishing property state to {topic}: {payload}")
            self.mqtt_client.publish(topic, payload, qos=1, retain=True)

            # Persist switch state
            self._persist_state(property_name, value)

    def _get_state_file_path(self) -> Path:
        """Get the path to the state file for this device."""
        return self.state_cache_dir / f"bloc9_{self.device_id}.json"

    def _persist_state(self, property_name: str, value: Any):
        """Persist a property state to disk."""
        try:
            # Ensure state cache directory exists
            self.state_cache_dir.mkdir(parents=True, exist_ok=True)

            state_file = self._get_state_file_path()

            # Load existing state or create new
            if state_file.exists():
                with open(state_file, "r") as f:
                    state_data = json.load(f)
            else:
                state_data = {}

            # Update state
            state_data[property_name] = value

            # Write back to file
            with open(state_file, "w") as f:
                json.dump(state_data, f, indent=2)

            self.logger.debug(f"Persisted state: {property_name}={value}")
        except Exception as e:
            self.logger.error(f"Failed to persist state for {property_name}: {e}")

    def _load_persisted_state(self) -> Dict[str, Any]:
        """Load persisted state from disk."""
        state_file = self._get_state_file_path()

        if not state_file.exists():
            self.logger.debug("No persisted state found")
            return {}

        try:
            with open(state_file, "r") as f:
                state_data = json.load(f)
            self.logger.info(
                f"Loaded persisted state with {len(state_data)} properties"
            )
            return state_data
        except Exception as e:
            self.logger.error(f"Failed to load persisted state: {e}")
            return {}

    def _load_and_publish_persisted_state(self):
        """Load persisted state and publish to MQTT as initial state."""
        persisted_state = self._load_persisted_state()

        if not persisted_state:
            return

        self.logger.info(
            f"Publishing {len(persisted_state)} persisted properties to MQTT"
        )

        for property_name, value in persisted_state.items():
            try:
                # Handle brightness properties
                if property_name.endswith("_brightness"):
                    base_prop = property_name.replace("_brightness", "")
                    brightness_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{base_prop}/brightness"
                    payload = str(value) if value is not None else "?"
                    self.logger.debug(
                        f"Restoring brightness to {brightness_topic}: {payload}"
                    )
                    self.mqtt_client.publish(
                        brightness_topic, payload, qos=1, retain=True
                    )
                # Skip stat properties
                elif property_name.startswith("stat"):
                    continue
                # Handle regular switch state
                else:
                    topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{property_name}/state"
                    payload = str(value) if value is not None else "?"
                    self.logger.debug(f"Restoring switch state to {topic}: {payload}")
                    self.mqtt_client.publish(topic, payload, qos=1, retain=True)
            except Exception as e:
                self.logger.error(f"Failed to restore state for {property_name}: {e}")


# Device type registry - maps device type names to classes
DEVICE_TYPE_CLASSES = {
    "bloc9": Bloc9,
    # Add more device types here:
    # "tank_sensor": TankSensor,
    # "battery_monitor": BatteryMonitor,
}


def create_device(
    device_type: str,
    device_id: int,
    device_config: Dict[str, Any],
    mqtt_client,
    mqtt_topic_prefix: str,
    can_bus,
    data_dir: Optional[str] = None,
) -> ScheiberCanDevice:
    """Factory function to create appropriate device instance."""
    device_class = DEVICE_TYPE_CLASSES.get(device_type, ScheiberCanDevice)

    # ScheiberCanDevice is abstract, so if no specific class found, use Bloc9 as default
    if device_class == ScheiberCanDevice:
        logging.warning(
            f"No device class found for type '{device_type}', using Bloc9 as default"
        )
        device_class = Bloc9

    return device_class(
        device_type,
        device_id,
        device_config,
        mqtt_client,
        mqtt_topic_prefix,
        can_bus,
        data_dir,
    )
