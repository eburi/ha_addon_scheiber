"""
MQTT entities for generator control through a Scheiber SourceSelector node.

One :class:`~scheiber.generator.GeneratorControl` is exposed as:

- ``switch.<entity_id>``: ON sends start, OFF sends stop, state mirrors the
  running flag reported by the node.
- ``button.<entity_id>_start`` / ``button.<entity_id>_stop``: explicit
  one-shot commands for automations.
- ``binary_sensor.<entity_id>_running`` (``device_class: running``).
- ``sensor.<entity_id>_phase``: diagnostic text (starting, running, ...).

The three measurement sensors (voltage, frequency, battery voltage) go through
the regular :class:`~can_mqtt_bridge.sensor.MQTTSensor` path.

Command safety: retained MQTT commands are never executed. A broker replay
after a restart must not be able to start or stop the engine, so any retained
payload on a command topic is cleared and ignored. ``read_only`` is honoured
in every command path, and the hardware interlock's refusal is logged and the
current state is republished so Home Assistant snaps the switch back.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt

from scheiber.generator import GeneratorInterlockError

from .discovery_name import format_discovery_name

DEVICE_INFO = {
    "identifiers": ["scheiber_system"],
    "name": "Scheiber",
    "model": "Marine Lighting Control System",
    "manufacturer": "Scheiber",
}


class _GeneratorEntityBase:
    """Shared topic layout and publishing helpers for generator entities."""

    component = "sensor"
    suffix = ""

    def __init__(
        self,
        generator: Any,
        device_type: str,
        device_id: int,
        mqtt_client: mqtt.Client,
        segment_id: int = 0,
        mqtt_topic_prefix: str = "homeassistant",
        read_only: bool = False,
    ):
        self.generator = generator
        self.device_type = device_type
        self.device_id = device_id
        self.segment_id = segment_id
        self.mqtt_client = mqtt_client
        self.mqtt_topic_prefix = mqtt_topic_prefix
        self.read_only = read_only

        self.device_slug = (
            f"{device_id}" if segment_id == 0 else f"{device_id}_{segment_id}"
        )
        self.entity_id = f"{generator.entity_id}{self.suffix}"
        self.logger = logging.getLogger(f"{__name__}.{self.entity_id}")
        self.unique_id = (
            f"scheiber_{device_type}_{self.device_slug}_generator{self.suffix}"
        )
        self.discovery_name = format_discovery_name(self.entity_id)

        base_topic = (
            f"{mqtt_topic_prefix}/scheiber/{device_type}/{self.device_slug}/generator"
        )
        self.base_topic = base_topic
        self.config_topic = (
            f"{mqtt_topic_prefix}/{self.component}/{self.entity_id}/config"
        )
        self.availability_topic = f"{base_topic}/availability"
        self.state_topic: Optional[str] = None
        self.command_topic: Optional[str] = None

    def _discovery_base(self) -> Dict[str, Any]:
        return {
            "name": self.discovery_name,
            "unique_id": self.unique_id,
            "availability_topic": self.availability_topic,
            "device": dict(DEVICE_INFO),
        }

    def _publish_discovery(self, config: Dict[str, Any]) -> None:
        self.mqtt_client.publish(
            self.config_topic, json.dumps(config), retain=True, qos=1
        )
        self.logger.debug("Published discovery config")

    def publish_availability(self, available: bool = True) -> None:
        payload = "online" if available else "offline"
        self.mqtt_client.publish(self.availability_topic, payload, retain=True, qos=1)

    def publish_initial_state(self) -> None:
        self.publish_state()

    def publish_state(self) -> None:
        """Entities without state do nothing."""

    def subscribe_to_updates(self) -> None:
        """Updates are wired through the generator observer in __init__."""

    def subscribe_to_commands(self) -> None:
        if self.command_topic:
            self.mqtt_client.subscribe(self.command_topic)
            self.logger.debug(f"Subscribed to commands at {self.command_topic}")

    def matches_topic(self, topic: str) -> bool:
        return self.command_topic is not None and topic == self.command_topic

    def handle_command(
        self, payload: str, is_retained: bool = False, timestamp: Optional[float] = None
    ) -> None:
        """Entities without a command topic ignore commands."""

    # Command helpers -------------------------------------------------

    def _guard_command(self, payload: str, is_retained: bool) -> bool:
        """Return True when the command may be acted on."""
        if self.read_only:
            self.logger.debug("Ignoring command (read-only mode)")
            return False
        if is_retained:
            self.logger.warning(
                f"Ignoring retained generator command '{payload}' on "
                f"{self.command_topic}; clearing it"
            )
            self.mqtt_client.publish(self.command_topic, None, retain=True)
            return False
        return True

    def _run_command(self, action: str, func) -> bool:
        try:
            func()
            return True
        except GeneratorInterlockError as exc:
            self.logger.warning(f"Generator {action} refused: {exc}")
        except Exception as exc:
            self.logger.error(f"Error sending generator {action}: {exc}")
        return False


class MQTTGeneratorSwitch(_GeneratorEntityBase):
    """Home Assistant switch: ON starts, OFF stops, state follows the node."""

    component = "switch"
    suffix = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state_topic = f"{self.base_topic}/state"
        self.command_topic = f"{self.base_topic}/set"
        self.generator.subscribe(self._on_generator_state_change)

    def publish_discovery(self) -> None:
        config = self._discovery_base()
        config.update(
            {
                "state_topic": self.state_topic,
                "command_topic": self.command_topic,
                "optimistic": False,
                "payload_on": "ON",
                "payload_off": "OFF",
                "state_on": "ON",
                "state_off": "OFF",
                "icon": "mdi:engine",
            }
        )
        self._publish_discovery(config)

    def publish_state(self) -> None:
        running = self.generator.running
        if running is None:
            self.logger.debug("Generator state unknown, not publishing")
            return
        payload = "ON" if running else "OFF"
        self.mqtt_client.publish(self.state_topic, payload, retain=True, qos=1)
        self.logger.info(f"Published state to {self.state_topic}: {payload}")

    def _on_generator_state_change(self, state: Dict[str, Any]) -> None:
        self.publish_state()

    def handle_command(
        self, payload: str, is_retained: bool = False, timestamp: Optional[float] = None
    ) -> None:
        if not self._guard_command(payload, is_retained):
            return
        wanted = payload.strip().upper()
        if wanted == "ON":
            self.logger.info("Switch command ON: starting generator")
            ok = self._run_command("start", self.generator.start)
        elif wanted == "OFF":
            self.logger.info("Switch command OFF: stopping generator")
            ok = self._run_command("stop", self.generator.stop)
        else:
            self.logger.warning(f"Unsupported generator switch payload '{payload}'")
            ok = False
        if not ok:
            # Snap the Home Assistant toggle back to the real state.
            self.publish_state()


class MQTTGeneratorButton(_GeneratorEntityBase):
    """Explicit start or stop button."""

    component = "button"

    def __init__(self, action: str, *args, **kwargs):
        if action not in ("start", "stop"):
            raise ValueError(f"Unsupported generator button action '{action}'")
        self.action = action
        self.suffix = f"_{action}"
        super().__init__(*args, **kwargs)
        self.command_topic = f"{self.base_topic}/{action}/set"

    def publish_discovery(self) -> None:
        config = self._discovery_base()
        config.update(
            {
                "command_topic": self.command_topic,
                "payload_press": "PRESS",
                "icon": "mdi:engine" if self.action == "start" else "mdi:engine-off",
            }
        )
        self._publish_discovery(config)

    def handle_command(
        self, payload: str, is_retained: bool = False, timestamp: Optional[float] = None
    ) -> None:
        if not self._guard_command(payload, is_retained):
            return
        func = self.generator.start if self.action == "start" else self.generator.stop
        self.logger.info(f"Button pressed: generator {self.action}")
        self._run_command(self.action, func)


class MQTTGeneratorRunning(_GeneratorEntityBase):
    """Binary sensor mirroring the node's running flag."""

    component = "binary_sensor"
    suffix = "_running"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state_topic = f"{self.base_topic}/running/state"
        self.generator.subscribe(self._on_generator_state_change)

    def publish_discovery(self) -> None:
        config = self._discovery_base()
        config.update(
            {
                "state_topic": self.state_topic,
                "device_class": "running",
                "payload_on": "ON",
                "payload_off": "OFF",
            }
        )
        self._publish_discovery(config)

    def publish_state(self) -> None:
        running = self.generator.running
        if running is None:
            return
        payload = "ON" if running else "OFF"
        self.mqtt_client.publish(self.state_topic, payload, retain=True, qos=1)
        self.logger.info(f"Published state to {self.state_topic}: {payload}")

    def _on_generator_state_change(self, state: Dict[str, Any]) -> None:
        self.publish_state()


class MQTTGeneratorPhase(_GeneratorEntityBase):
    """Diagnostic text sensor with the decoded control phase."""

    component = "sensor"
    suffix = "_phase"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state_topic = f"{self.base_topic}/phase/state"
        self.generator.subscribe(self._on_generator_state_change)

    def publish_discovery(self) -> None:
        config = self._discovery_base()
        config.update(
            {
                "state_topic": self.state_topic,
                "entity_category": "diagnostic",
                "icon": "mdi:state-machine",
            }
        )
        self._publish_discovery(config)

    def publish_state(self) -> None:
        phase = self.generator.phase_name
        if phase is None:
            return
        self.mqtt_client.publish(self.state_topic, phase, retain=True, qos=1)
        self.logger.info(f"Published state to {self.state_topic}: {phase}")

    def _on_generator_state_change(self, state: Dict[str, Any]) -> None:
        self.publish_state()


def create_generator_entities(
    generator: Any,
    device_type: str,
    device_id: int,
    mqtt_client: mqtt.Client,
    segment_id: int = 0,
    mqtt_topic_prefix: str = "homeassistant",
    read_only: bool = False,
):
    """Build the full entity set for one generator control."""
    common = dict(
        generator=generator,
        device_type=device_type,
        device_id=device_id,
        mqtt_client=mqtt_client,
        segment_id=segment_id,
        mqtt_topic_prefix=mqtt_topic_prefix,
        read_only=read_only,
    )
    return [
        MQTTGeneratorSwitch(**common),
        MQTTGeneratorButton("start", **common),
        MQTTGeneratorButton("stop", **common),
        MQTTGeneratorRunning(**common),
        MQTTGeneratorPhase(**common),
    ]
