"""
MQTT Bridge for Scheiber sensor entities.
"""

import json
import logging
from typing import Any
import paho.mqtt.client as mqtt


class MQTTSensor:
    """
    MQTT Sensor entity with Home Assistant Discovery support.

    Each sensor instance handles its own:
    - Discovery config publishing
    - State publishing (observer pattern)
    - Availability management
    """

    def __init__(
        self,
        hardware_sensor: Any,
        device_type: str,
        device_id: int,
        mqtt_client: mqtt.Client,
        mqtt_topic_prefix: str = "homeassistant",
    ):
        """
        Initialize MQTT Sensor.

        Args:
            hardware_sensor: Sensor instance from scheiber module (Voltage or Level)
            device_type: Device type (e.g., 'bloc7')
            device_id: Device bus ID
            mqtt_client: MQTT client instance
            mqtt_topic_prefix: MQTT topic prefix
        """
        self.logger = logging.getLogger(f"{__name__}.{hardware_sensor.entity_id}")
        self.sensor = hardware_sensor
        self.device_type = device_type
        self.device_id = device_id
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix

        # Generate identifiers
        sensor_name_slug = self.sensor.name.lower().replace(" ", "_")
        self.unique_id = f"scheiber_{device_type}_{device_id}_{sensor_name_slug}"
        self.entity_id = hardware_sensor.entity_id

        # Generate topics
        base_topic = (
            f"{mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{sensor_name_slug}"
        )
        self.config_topic = f"{mqtt_topic_prefix}/sensor/{self.entity_id}/config"
        self.state_topic = f"{base_topic}/state"
        self.availability_topic = f"{base_topic}/availability"

        # Subscribe to hardware state changes
        hardware_sensor.subscribe(self._on_hardware_state_change)

    def publish_discovery(self):
        """Publish Home Assistant MQTT Discovery config."""
        discovery_config = {
            "name": self.sensor.name,
            "unique_id": self.unique_id,
            "state_topic": self.state_topic,
            "availability_topic": self.availability_topic,
            "device": {
                "identifiers": ["scheiber_system"],
                "name": "Scheiber",
                "model": "Marine Lighting Control System",
                "manufacturer": "Scheiber",
            },
            "unit_of_measurement": self.sensor.unit_of_measurement,
        }

        # Add device class for voltage sensors
        if hasattr(self.sensor, "device_class") and self.sensor.device_class:
            discovery_config["device_class"] = self.sensor.device_class
            discovery_config["state_class"] = "measurement"
        elif hasattr(self.sensor, "icon") and self.sensor.icon:
            # For sensors without device_class, add icon
            discovery_config["icon"] = self.sensor.icon
            discovery_config["state_class"] = "measurement"

        self.mqtt_client.publish(
            self.config_topic, json.dumps(discovery_config), retain=True, qos=1
        )
        self.logger.debug(f"Published discovery config")

    def publish_availability(self, available: bool = True):
        """Publish availability status."""
        payload = "online" if available else "offline"
        self.mqtt_client.publish(self.availability_topic, payload, retain=True, qos=1)

    def publish_initial_state(self):
        """Publish initial state from hardware."""
        self._publish_state()

    def _on_hardware_state_change(self, state_dict):
        """
        Handle hardware state changes and publish to MQTT.

        Args:
            state_dict: State dictionary from hardware sensor (contains 'value')
        """
        self._publish_state()

    def _publish_state(self):
        """Publish the current sensor value to MQTT."""
        value = self.sensor.get_value()
        if value is not None:
            self.mqtt_client.publish(self.state_topic, str(value), retain=True, qos=1)
            self.logger.debug(f"Published state: {value}")

    def matches_topic(self, topic: str) -> bool:
        """Sensors don't subscribe to command topics."""
        return False

    def handle_command(self, topic: str, payload: str):
        """Sensors don't handle commands."""
        pass
