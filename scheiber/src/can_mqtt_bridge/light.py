"""
Light entity for MQTT Bridge.

Handles MQTT discovery, state publishing, and command handling for lights.
"""

import json
import logging
from typing import Dict, Any, Callable
import paho.mqtt.client as mqtt


class MQTTLight:
    """
    MQTT Light entity with Home Assistant Discovery support.

    Each light instance handles its own:
    - Discovery config publishing
    - State publishing (observer pattern)
    - Command topic subscription
    - Command parsing and execution
    """

    def __init__(
        self,
        hardware_light,
        device_type: str,
        device_id: int,
        mqtt_client: mqtt.Client,
        mqtt_topic_prefix: str = "homeassistant",
        read_only: bool = False,
    ):
        """
        Initialize MQTT Light.

        Args:
            hardware_light: DimmableLight instance from scheiber module
            device_type: Device type (e.g., 'bloc9')
            device_id: Device bus ID
            mqtt_client: MQTT client instance
            mqtt_topic_prefix: MQTT topic prefix
            read_only: Read-only mode (no commands)
        """
        self.logger = logging.getLogger(f"{__name__}.{hardware_light.entity_id}")
        self.hardware_light = hardware_light
        self.device_type = device_type
        self.device_id = device_id
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.read_only = read_only

        # Generate identifiers (using s1, s2, etc. naming from hardware)
        self.switch_name = f"s{hardware_light.switch_nr + 1}"  # e.g., 's1', 's2'
        self.unique_id = f"scheiber_{device_type}_{device_id}_{self.switch_name}"
        self.entity_id = hardware_light.entity_id  # e.g., 'main_light_crew_cabin'

        # Generate topics (v5 schema)
        base_topic = (
            f"{mqtt_topic_prefix}/scheiber/{device_type}/{device_id}/{self.switch_name}"
        )
        self.config_topic = f"{mqtt_topic_prefix}/light/{self.entity_id}/config"
        self.state_topic = f"{base_topic}/state"
        self.availability_topic = f"{base_topic}/availability"
        self.command_topic = f"{base_topic}/set"

        # Subscribe to hardware state changes
        hardware_light.subscribe(self._on_hardware_state_change)

    def publish_discovery(self):
        """Publish Home Assistant MQTT Discovery config."""
        discovery_config = {
            "name": self.hardware_light.name,
            "unique_id": self.unique_id,
            "state_topic": self.state_topic,
            "command_topic": self.command_topic,
            "availability_topic": self.availability_topic,
            "optimistic": False,
            "device": {
                "identifiers": ["scheiber_system"],
                "name": "Scheiber",
                "model": "Marine Lighting Control System",
                "manufacturer": "Scheiber",
            },
            "schema": "json",
            "brightness": True,
            "supported_color_modes": ["brightness"],
            "brightness_scale": 255,
            "flash": True,
            "flash_time_short": 2,
            "flash_time_long": 10,
            "effect": True,
            "effect_list": [
                "linear",
                "ease_in_sine",
                "ease_out_sine",
                "ease_in_out_sine",
                "ease_in_quad",
                "ease_out_quad",
                "ease_in_out_quad",
                "ease_in_cubic",
                "ease_out_cubic",
                "ease_in_out_cubic",
                "ease_in_quart",
                "ease_out_quart",
                "ease_in_out_quart",
            ],
        }

        self.mqtt_client.publish(
            self.config_topic, json.dumps(discovery_config), retain=True, qos=1
        )
        self.logger.debug(f"Published discovery config")

    def publish_availability(self, available: bool = True):
        """Publish availability status."""
        payload = "online" if available else "offline"
        self.mqtt_client.publish(self.availability_topic, payload, retain=True, qos=1)

    def subscribe_to_commands(self):
        """Subscribe to command topic."""
        self.mqtt_client.subscribe(self.command_topic)
        self.logger.debug(f"Subscribed to commands at {self.command_topic}")

    def publish_initial_state(self):
        """Publish initial state from hardware."""
        state = self.hardware_light.get_state()
        self._on_hardware_state_change(state)

    def _on_hardware_state_change(self, state_dict: Dict[str, Any]):
        """
        Handle hardware state changes and publish to MQTT.

        Args:
            state_dict: State dictionary from hardware light
        """
        json_state = {}
        if "state" in state_dict:
            json_state["state"] = "ON" if state_dict["state"] else "OFF"
        if "brightness" in state_dict:
            json_state["brightness"] = state_dict["brightness"]

        if json_state:
            payload = json.dumps(json_state)
            self.mqtt_client.publish(self.state_topic, payload, retain=True, qos=1)
            self.logger.debug(f"Published state: {payload}")

    def handle_command(self, payload: str):
        """
        Handle incoming MQTT command.

        Args:
            payload: JSON command payload
        """
        if self.read_only:
            self.logger.debug("Ignoring command (read-only mode)")
            return

        try:
            # Parse JSON command
            try:
                command = json.loads(payload)
            except json.JSONDecodeError:
                # Simple ON/OFF command
                command = {"state": payload}

            state = command.get("state", "ON")
            brightness = command.get("brightness")
            transition = command.get("transition")
            flash = command.get("flash")
            effect = command.get("effect")

            # Execute command
            if flash:
                # Flash effect
                count = 3 if flash == "short" else 5
                self.logger.info(f"Flashing {count} times")
                self.hardware_light.flash(count=count)
            elif transition:
                # Fade transition with optional easing effect
                target = (
                    brightness
                    if brightness is not None
                    else (255 if state == "ON" else 0)
                )
                duration = transition
                easing = effect if effect else "ease_in_out_sine"
                self.logger.info(f"Fading to {target} over {duration}s with {easing}")
                self.hardware_light.fade_to(target, duration=duration, easing=easing)
            elif brightness is not None:
                # Set brightness
                self.logger.info(f"Setting brightness to {brightness}")
                self.hardware_light.set_brightness(brightness)
            else:
                # Simple ON/OFF
                target = 255 if state == "ON" else 0
                self.logger.info(f"Setting to {state}")
                self.hardware_light.set_brightness(target)

        except Exception as e:
            self.logger.error(f"Error handling command: {e}")

    def matches_topic(self, topic: str) -> bool:
        """
        Check if this light handles the given topic.

        Args:
            topic: MQTT topic

        Returns:
            True if this light handles the topic
        """
        return topic == self.command_topic
