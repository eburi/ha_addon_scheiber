"""
MQTT binary sensor for the system-wide Scheiber stale-output indicator.
"""

import logging
from typing import Any

import paho.mqtt.client as mqtt


class MQTTStaleIndicator:
    """
    System-level Home Assistant binary sensor reporting stale Bloc9 outputs.

    A Bloc9 can get stuck in the hold-to-dim cycle used by air switches for
    brightness adjustment. It then keeps broadcasting a brightness setpoint
    while the output stays de-energised, so the lamp is dark but the system is
    misbehaving. This entity aggregates that condition across every device on
    the bus so a single automation can notify on it.

    Published as device_class "problem": ON means at least one output is stale.
    """

    ENTITY_ID = "scheiber_stale_outputs"

    def __init__(
        self,
        system: Any,
        mqtt_client: mqtt.Client,
        mqtt_topic_prefix: str = "homeassistant",
    ):
        """
        Initialize the stale indicator.

        Args:
            system: ScheiberSystem instance
            mqtt_client: MQTT client instance
            mqtt_topic_prefix: MQTT topic prefix
        """
        self.logger = logging.getLogger(f"{__name__}.{self.ENTITY_ID}")
        self.system = system
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix

        self.unique_id = f"scheiber_{self.ENTITY_ID}"
        self.entity_id = self.ENTITY_ID

        base_topic = f"{mqtt_topic_prefix}/scheiber/system/stale_outputs"
        self.config_topic = f"{mqtt_topic_prefix}/binary_sensor/{self.entity_id}/config"
        self.state_topic = f"{base_topic}/state"
        self.availability_topic = f"{base_topic}/availability"

        system.subscribe_to_stale_change(self._on_stale_change)

    def publish_discovery(self) -> None:
        """Publish Home Assistant MQTT Discovery config."""
        import json

        discovery_config = {
            "name": "Stale Outputs",
            "unique_id": self.unique_id,
            "state_topic": self.state_topic,
            "availability_topic": self.availability_topic,
            "device_class": "problem",
            "payload_on": "ON",
            "payload_off": "OFF",
            "entity_category": "diagnostic",
            "device": {
                "identifiers": ["scheiber_system"],
                "name": "Scheiber",
                "model": "Marine Lighting Control System",
                "manufacturer": "Scheiber",
            },
        }

        try:
            self.mqtt_client.publish(
                self.config_topic, json.dumps(discovery_config), retain=True
            )
            self.logger.info(f"Published discovery to {self.config_topic}")
        except Exception as e:
            self.logger.error(f"Failed to publish discovery: {e}")

    def publish_availability(self, available: bool = True) -> None:
        """Publish availability."""
        try:
            self.mqtt_client.publish(
                self.availability_topic,
                "online" if available else "offline",
                retain=True,
            )
        except Exception as e:
            self.logger.error(f"Failed to publish availability: {e}")

    def publish_state(self) -> None:
        """Publish the current aggregate state."""
        self._publish(self.system.has_stale_outputs())

    def _on_stale_change(self, active: bool) -> None:
        """Handle a change of the system-wide stale aggregate."""
        self._publish(active)

    def _publish(self, active: bool) -> None:
        payload = "ON" if active else "OFF"
        try:
            self.mqtt_client.publish(self.state_topic, payload, retain=True)
            self.logger.info(f"Published state to {self.state_topic}: {payload}")
        except Exception as e:
            self.logger.error(f"Failed to publish state: {e}")
