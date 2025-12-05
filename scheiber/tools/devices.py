#!/usr/bin/env python3
"""
Device class hierarchy for Scheiber CAN devices.

Base class ScheiberCanDevice provides common functionality.
Subclasses (Light, etc.) add device-specific behavior.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Set


class ScheiberCanDevice(ABC):
    """Base class for all Scheiber CAN devices."""

    def __init__(
        self,
        device_type: str,
        device_id: int,
        device_config: Dict[str, Any],
        mqtt_client,
        mqtt_topic_prefix: str,
    ):
        self.device_type = device_type
        self.device_id = device_id
        self.device_config = device_config
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}.{device_type}_{device_id}"
        )

        # Track device state: {property_name: value}
        self.state = {}

        # Track which properties have been published
        self.published_properties = set()

    def get_all_properties(self) -> Set[str]:
        """Get all unique properties across all matchers for this device."""
        all_properties = set()
        for matcher in self.device_config.get("matchers", []):
            all_properties.update(matcher.get("properties", {}).keys())
        return all_properties

    def update_state(self, decoded_properties: Dict[str, Any]):
        """Update device state with decoded properties."""
        self.state.update(decoded_properties)

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
        topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}"
        payload = {
            "name": self.device_config.get("name", self.device_type),
            "device_type": self.device_type,
            "bus_id": self.device_id,
        }
        import json

        payload_json = json.dumps(payload)
        self.logger.debug(f"Publishing device info to {topic}: {payload_json}")
        self.mqtt_client.publish(topic, payload_json, qos=1, retain=True)


class Light(ScheiberCanDevice):
    """Light device with brightness support (e.g., Bloc9 switches)."""

    def __init__(
        self,
        device_type: str,
        device_id: int,
        device_config: Dict[str, Any],
        mqtt_client,
        mqtt_topic_prefix: str,
    ):
        super().__init__(
            device_type, device_id, device_config, mqtt_client, mqtt_topic_prefix
        )
        self.logger.info(f"Initialized Light device: {device_type} {device_id}")

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

            config_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{prop_name}/config"
            state_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{prop_name}/state"

            config_payload = {
                "name": f"{self.device_config.get('name', self.device_type)} {self.device_id} {prop_name.upper()}",
                "unique_id": unique_id,
                "default_entity_id": default_entity_id,
                "device_class": "light",
                "state_topic": state_topic,
                "command_topic": f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{prop_name}/set",
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
                config_payload["brightness_state_topic"] = (
                    f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{prop_name}/brightness"
                )
                config_payload["brightness_command_topic"] = (
                    f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{prop_name}/set_brightness"
                )
                config_payload["brightness_scale"] = 100

                # Publish initial brightness value
                brightness_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{prop_name}/brightness"
                self.logger.debug(
                    f"Publishing initial brightness to {brightness_topic}: ?"
                )
                self.mqtt_client.publish(brightness_topic, "?", qos=1, retain=True)

            config_json = json.dumps(config_payload)
            self.logger.debug(
                f"Publishing HA discovery config to {config_topic}: {config_json}"
            )
            self.mqtt_client.publish(config_topic, config_json, qos=1, retain=True)

            self.published_properties.add(prop_name)

    def publish_state(self, property_name: str, value: Any):
        """Publish property state to MQTT, handling brightness separately."""
        # Handle brightness properties
        if property_name.endswith("_brightness"):
            base_prop = property_name.replace("_brightness", "")
            brightness_topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{base_prop}/brightness"
            payload = str(value) if value is not None else "?"
            self.logger.debug(f"Publishing brightness to {brightness_topic}: {payload}")
            self.mqtt_client.publish(brightness_topic, payload, qos=1, retain=True)
        # Skip stat properties
        elif property_name.startswith("stat"):
            return
        # Handle regular switch state
        else:
            topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{property_name}/state"
            payload = str(value) if value is not None else "?"
            self.logger.debug(f"Publishing property state to {topic}: {payload}")
            self.mqtt_client.publish(topic, payload, qos=1, retain=True)


# Device type registry - maps device type names to classes
DEVICE_TYPE_CLASSES = {
    "bloc9": Light,
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
) -> ScheiberCanDevice:
    """Factory function to create appropriate device instance."""
    device_class = DEVICE_TYPE_CLASSES.get(device_type, ScheiberCanDevice)

    # ScheiberCanDevice is abstract, so if no specific class found, use Light as default
    if device_class == ScheiberCanDevice:
        logging.warning(
            f"No device class found for type '{device_type}', using Light as default"
        )
        device_class = Light

    return device_class(
        device_type, device_id, device_config, mqtt_client, mqtt_topic_prefix
    )
