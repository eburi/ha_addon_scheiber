"""Logical MQTT entities that fan out to multiple Bloc9 outputs."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt

from .discovery_name import format_discovery_name


class MQTTLogicalLight:
    """Expose multiple physical Bloc9 lights as one logical HA light."""

    def __init__(
        self,
        hardware_lights,
        mqtt_client: mqtt.Client,
        mqtt_topic_prefix: str = "homeassistant",
        read_only: bool = False,
    ):
        self.hardware_lights = list(hardware_lights)
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.read_only = read_only
        self.entity_id = self.hardware_lights[0].entity_id
        self.discovery_name = format_discovery_name(self.entity_id)
        self.unique_id = f"scheiber_logical_light_{self.entity_id}"
        base_topic = f"{mqtt_topic_prefix}/scheiber/logical/light/{self.entity_id}"
        self.config_topic = f"{mqtt_topic_prefix}/light/{self.entity_id}/config"
        self.state_topic = f"{base_topic}/state"
        self.availability_topic = f"{base_topic}/availability"
        self.command_topic = f"{base_topic}/set"
        self.logger = logging.getLogger(f"{__name__}.{self.entity_id}")

        for hardware_light in self.hardware_lights:
            hardware_light.subscribe(self._on_hardware_state_change)

    def publish_discovery(self):
        discovery_config = {
            "name": self.discovery_name,
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

    def publish_availability(self, available: bool = True):
        payload = "online" if available else "offline"
        self.mqtt_client.publish(self.availability_topic, payload, retain=True, qos=1)

    def subscribe_to_commands(self):
        self.mqtt_client.subscribe(self.command_topic)

    def publish_initial_state(self):
        self._publish_state(self._aggregate_state())

    def _aggregate_state(self) -> Dict[str, Any]:
        states = [member.get_state() for member in self.hardware_lights]
        on_states = [state for state in states if state.get("state")]
        return {
            "state": bool(on_states),
            "brightness": max(
                (int(state.get("brightness", 0)) for state in on_states),
                default=0,
            ),
        }

    def _publish_state(self, state_dict: Dict[str, Any]):
        payload = json.dumps(
            {
                "state": "ON" if state_dict.get("state") else "OFF",
                "brightness": int(state_dict.get("brightness", 0)),
            }
        )
        self.mqtt_client.publish(self.state_topic, payload, retain=True, qos=1)

    def _on_hardware_state_change(self, _state_dict: Dict[str, Any]):
        self._publish_state(self._aggregate_state())

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
            try:
                command = json.loads(payload)
            except json.JSONDecodeError:
                command = {"state": payload}

            state = command.get("state", "ON")
            brightness = command.get("brightness")
            transition = command.get("transition")
            flash = command.get("flash")
            effect = command.get("effect")

            for hardware_light in self.hardware_lights:
                if flash:
                    hardware_light.flash()
                elif transition:
                    target = (
                        brightness
                        if brightness is not None
                        else (255 if state == "ON" else 0)
                    )
                    easing = effect if effect else hardware_light._default_easing
                    hardware_light.fade_to(target, duration=transition, easing=easing)
                elif brightness is not None or effect:
                    hardware_light.set(
                        state=state == "ON",
                        brightness=brightness,
                        effect=effect,
                    )
                else:
                    hardware_light.set_brightness(255 if state == "ON" else 0)

            if is_retained:
                self.mqtt_client.publish(self.command_topic, None, retain=True)
        except Exception as exc:
            self.logger.error(f"Error handling logical light command: {exc}")

    def matches_topic(self, topic: str) -> bool:
        return topic == self.command_topic


class MQTTLogicalSwitch:
    """Expose multiple physical Bloc9 switches as one logical HA switch."""

    def __init__(
        self,
        hardware_switches,
        mqtt_client: mqtt.Client,
        mqtt_topic_prefix: str = "homeassistant",
        read_only: bool = False,
    ):
        self.hardware_switches = list(hardware_switches)
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.read_only = read_only
        self.entity_id = self.hardware_switches[0].entity_id
        self.discovery_name = format_discovery_name(self.entity_id)
        self.unique_id = f"scheiber_logical_switch_{self.entity_id}"
        base_topic = f"{mqtt_topic_prefix}/scheiber/logical/switch/{self.entity_id}"
        self.config_topic = f"{mqtt_topic_prefix}/switch/{self.entity_id}/config"
        self.state_topic = f"{base_topic}/state"
        self.availability_topic = f"{base_topic}/availability"
        self.command_topic = f"{base_topic}/set"
        self.logger = logging.getLogger(f"{__name__}.{self.entity_id}")

        for hardware_switch in self.hardware_switches:
            hardware_switch.subscribe(self._on_hardware_state_change)

    def publish_discovery(self):
        discovery_config = {
            "name": self.discovery_name,
            "unique_id": self.unique_id,
            "state_topic": self.state_topic,
            "command_topic": self.command_topic,
            "availability_topic": self.availability_topic,
            "optimistic": False,
            "device_class": "switch",
            "payload_on": "ON",
            "payload_off": "OFF",
            "state_on": "ON",
            "state_off": "OFF",
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
        self._publish_state("ON" if self._aggregate_state() else "OFF")

    def _aggregate_state(self) -> bool:
        return any(member.get_state() for member in self.hardware_switches)

    def _publish_state(self, payload: str):
        self.mqtt_client.publish(self.state_topic, payload, retain=True, qos=1)

    def _on_hardware_state_change(self, _state_dict: Dict[str, Any]):
        self._publish_state("ON" if self._aggregate_state() else "OFF")

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
            state_bool = payload.strip().upper() == "ON"
            for hardware_switch in self.hardware_switches:
                hardware_switch.set(state_bool)
            if is_retained:
                self.mqtt_client.publish(self.command_topic, None, retain=True)
        except Exception as exc:
            self.logger.error(f"Error handling logical switch command: {exc}")

    def matches_topic(self, topic: str) -> bool:
        return topic == self.command_topic
