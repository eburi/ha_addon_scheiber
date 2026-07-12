"""
MQTT Event entity for wireless Scheiber Air Switch buttons.

Air Switch buttons are incoming, stateless physical button presses (not
commands sent from Home Assistant), so unlike `MQTTButton` (which exposes a
Bloc9 pulse *output* as an HA `button` platform entity that HA can press),
this uses Home Assistant's MQTT `event` platform: HA subscribes to a state
topic carrying a JSON `{"event_type": "press"}` payload every time the
physical button is pressed.
"""

import json
import logging

import paho.mqtt.client as mqtt

from .discovery_name import format_discovery_name


class MQTTAirSwitchButton:
    """Expose a wireless Air Switch button as a Home Assistant event entity."""

    EVENT_TYPES = ["press"]

    def __init__(
        self,
        hardware_button,
        mqtt_client: mqtt.Client,
        mqtt_topic_prefix: str = "homeassistant",
    ):
        self.logger = logging.getLogger(f"{__name__}.{hardware_button.entity_id}")
        self.hardware_button = hardware_button
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix

        identity_slug = hardware_button.identity_hex.lower()
        self.unique_id = (
            f"scheiber_air_switch_{identity_slug}_btn{hardware_button.button_index}"
        )
        self.entity_id = hardware_button.entity_id
        self.discovery_name = format_discovery_name(self.entity_id)

        base_topic = (
            f"{mqtt_topic_prefix}/scheiber/air_switch/"
            f"{identity_slug}/btn{hardware_button.button_index}"
        )
        self.config_topic = f"{mqtt_topic_prefix}/event/{self.entity_id}/config"
        self.state_topic = f"{base_topic}/state"
        self.availability_topic = f"{base_topic}/availability"

        hardware_button.subscribe(self._on_hardware_event)

    def publish_discovery(self):
        discovery_config = {
            "name": self.discovery_name,
            "unique_id": self.unique_id,
            "state_topic": self.state_topic,
            "event_types": self.EVENT_TYPES,
            "device_class": "button",
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
        """Air Switch buttons are incoming-only; there is no command topic."""

    def publish_initial_state(self):
        """Air Switch buttons are stateless and do not publish an initial event."""

    def matches_topic(self, topic: str) -> bool:
        """Air Switch buttons do not accept commands."""
        return False

    def handle_command(self, payload, is_retained=False, timestamp=None):
        """Air Switch buttons do not accept commands."""

    def _on_hardware_event(self, event: dict) -> None:
        event_type = event.get("event_type", "press")
        if event_type not in self.EVENT_TYPES:
            self.logger.warning(f"Unknown Air Switch event type: {event_type}")
            return
        self.mqtt_client.publish(
            self.state_topic,
            json.dumps({"event_type": event_type}),
            retain=False,
            qos=1,
        )
        self.logger.debug(f"Published {event_type} event")
