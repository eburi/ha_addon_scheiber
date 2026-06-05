"""
Button entity for momentary Bloc9 pulse outputs.
"""

import json
import logging
import time
from typing import Optional

import paho.mqtt.client as mqtt

from .discovery_name import format_discovery_name


class MQTTButton:
    """Expose a pulse output as a Home Assistant button entity."""

    def __init__(
        self,
        hardware_pulse,
        device_type: str,
        device_id: int,
        mqtt_client: mqtt.Client,
        segment_id: int = 0,
        mqtt_topic_prefix: str = "homeassistant",
        read_only: bool = False,
    ):
        self.logger = logging.getLogger(f"{__name__}.{hardware_pulse.entity_id}")
        self.hardware_pulse = hardware_pulse
        self.device_type = device_type
        self.device_id = device_id
        self.segment_id = segment_id
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.read_only = read_only

        self.switch_name = f"s{hardware_pulse.switch_nr + 1}"
        self.device_slug = (
            f"{device_id}" if segment_id == 0 else f"{device_id}_{segment_id}"
        )
        self.unique_id = f"scheiber_{device_type}_{self.device_slug}_{self.switch_name}"
        self.entity_id = hardware_pulse.entity_id
        self.discovery_name = format_discovery_name(self.entity_id)
        base_topic = (
            f"{mqtt_topic_prefix}/scheiber/{device_type}/{self.device_slug}/{self.switch_name}"
        )
        self.config_topic = f"{mqtt_topic_prefix}/button/{self.entity_id}/config"
        self.availability_topic = f"{base_topic}/availability"
        self.command_topic = f"{base_topic}/set"

    def publish_discovery(self):
        discovery_config = {
            "name": self.discovery_name,
            "unique_id": self.unique_id,
            "command_topic": self.command_topic,
            "payload_press": "PRESS",
            "availability_topic": self.availability_topic,
            "device": {
                "identifiers": ["scheiber_system"],
                "name": "Scheiber",
                "model": "Marine Lighting Control System",
                "manufacturer": "Scheiber",
            },
        }
        self.mqtt_client.publish(
            self.config_topic, json.dumps(discovery_config), retain=True, qos=1
        )

    def publish_availability(self, available: bool = True):
        payload = "online" if available else "offline"
        self.mqtt_client.publish(self.availability_topic, payload, retain=True, qos=1)

    def subscribe_to_commands(self):
        self.mqtt_client.subscribe(self.command_topic)

    def publish_initial_state(self):
        """Buttons are stateless and do not publish state."""

    def handle_command(
        self, payload: str, is_retained: bool = False, timestamp: Optional[float] = None
    ):
        if self.read_only:
            self.logger.debug("Ignoring command (read-only mode)")
            return

        if is_retained and timestamp is not None:
            message_age = time.time() - timestamp
            if message_age > 300:
                self.mqtt_client.publish(self.command_topic, None, retain=True)
                return

        try:
            self.hardware_pulse.press()
            if is_retained:
                self.mqtt_client.publish(self.command_topic, None, retain=True)
        except Exception as exc:
            self.logger.error(f"Error handling button press: {exc}")

    def matches_topic(self, topic: str) -> bool:
        return topic == self.command_topic
