"""
MQTT Bridge for Scheiber sensor entities.
"""

import logging
from typing import Any
import paho.mqtt.client as mqtt

from .helpers import (
    publish_ha_discovery_config,
    get_ha_device_config,
    get_unique_id,
)

logger = logging.getLogger(__name__)


class MQTTSensor:
    """
    Manages the MQTT integration for a single Scheiber sensor (Voltage or Level).
    """

    def __init__(
        self,
        hardware_sensor: Any,
        device_type: str,
        device_id: str,
        mqtt_client: mqtt.Client,
        mqtt_topic_prefix: str,
    ):
        self.sensor = hardware_sensor
        self.device_type = device_type
        self.device_id = device_id
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix

        self.unique_id = get_unique_id(
            device_type, device_id, "sensor", self.sensor.name
        )
        self.topic_base = (
            f"{self.mqtt_topic_prefix}/sensor/scheiber_{self.device_id}/"
            f"{self.sensor.name.lower().replace(' ', '_')}"
        )
        self.state_topic = f"{self.topic_base}/state"
        self.availability_topic = f"{self.topic_base}/availability"

    def publish_discovery(self):
        """Publish the Home Assistant discovery configuration for this sensor."""
        config = {
            "name": self.sensor.name,
            "unique_id": self.unique_id,
            "state_topic": self.state_topic,
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "unit_of_measurement": self.sensor.unit_of_measurement,
            "device": get_ha_device_config(self.device_id, self.device_type),
        }

        # Add device class for voltage sensors
        if self.sensor.type == "voltage":
            config["device_class"] = "voltage"
        elif self.sensor.type == "level":
            # For tank levels, use appropriate icon without device_class
            config["icon"] = "mdi:gauge"
            config["state_class"] = "measurement"

        publish_ha_discovery_config(
            self.mqtt_client, self.topic_base, self.unique_id, config
        )
        logger.info(f"Published HA discovery for sensor '{self.sensor.name}'")

    def publish_availability(self, available: bool):
        """Publish the availability status of this sensor."""
        payload = "online" if available else "offline"
        self.mqtt_client.publish(self.availability_topic, payload, retain=True)

    def publish_state(self):
        """Publish the current state of the sensor."""
        if self.sensor.value is not None:
            self.mqtt_client.publish(
                self.state_topic, str(self.sensor.value), retain=True
            )

    def subscribe_to_updates(self):
        """Subscribe to updates from the hardware sensor."""
        self.sensor.subscribe(self.on_hardware_update)

    def on_hardware_update(self, sensor_instance):
        """Callback executed when the hardware sensor's state changes."""
        self.publish_state()

    def matches_topic(self, topic: str) -> bool:
        """This entity does not subscribe to any command topics."""
        return False

    def handle_command(self, payload: str, **kwargs):
        """This entity does not handle commands."""
        pass
