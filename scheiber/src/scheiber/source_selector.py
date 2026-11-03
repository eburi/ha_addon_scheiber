"""Scheiber SourceSelector monitoring and generator-control device."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base_device import ScheiberCanDevice
from .bloc7 import SENSOR_TYPES, SensorOutput, ValueConfig, create_sensor_output
from .generator import GeneratorControl
from .matchers import Matcher

logger = logging.getLogger(__name__)


class SourceSelectorDevice(ScheiberCanDevice):
    """SourceSelector sensor container with optional generator control.

    Source selectors switch high-power AC sources. By default this class
    exposes measurements only and has no command-sending API. When the
    configuration carries a ``generator`` section the node is the one wired to
    the generator's remote start/stop lines, and a :class:`GeneratorControl`
    is attached that can send the start and stop command frames.
    """

    def __init__(
        self,
        device_id: int,
        can_bus: Any,
        config: Dict[str, Any],
        segment_id: int = 0,
        logger=None,
    ):
        super().__init__(
            device_id, "source_selector", can_bus, segment_id=segment_id, logger=logger
        )
        self._sensors: List[SensorOutput] = []
        self._generator: Optional[GeneratorControl] = None

        for sensor_config in config.get("sensors", []) or []:
            sensor_type = sensor_config.get("sensor_type", "voltage")
            if sensor_type not in SENSOR_TYPES:
                raise ValueError(
                    f"Unsupported SourceSelector sensor_type: {sensor_type}"
                )
            matcher = Matcher(**sensor_config["matcher"])
            value_config = ValueConfig(**sensor_config["value_config"])
            entity_id = sensor_config.get(
                "entity_id", sensor_config["name"].lower().replace(" ", "_")
            )
            self._sensors.append(
                create_sensor_output(
                    sensor_type,
                    sensor_config["name"],
                    entity_id,
                    matcher,
                    value_config,
                )
            )

        generator_config = config.get("generator")
        if generator_config:
            name = generator_config.get("name") or "Generator"
            entity_id = generator_config.get("entity_id") or name.lower().replace(
                " ", "_"
            )
            self._generator = GeneratorControl(
                device_id=device_id,
                segment_id=segment_id,
                name=name,
                entity_id=entity_id,
                send_message_func=self._send_can_message,
                logger=self.logger.getChild("generator"),
            )

    def _send_can_message(self, arbitration_id: int, data: bytes) -> None:
        """Route generator commands through the bus wrapper (honours read_only)."""
        self.can_bus.send_message(arbitration_id, data)

    def get_matchers(self) -> List[Matcher]:
        """Return all matchers from configured sensors and the generator control."""
        matchers = [sensor.matcher for sensor in self._sensors]
        if self._generator is not None:
            matchers.extend(self._generator.get_matchers())
        return matchers

    def get_sensors(self) -> List[SensorOutput]:
        """Return configured sensors plus the generator's built-in measurements."""
        sensors = list(self._sensors)
        if self._generator is not None:
            sensors.extend(self._generator.get_sensors())
        return sensors

    def get_generators(self) -> List[GeneratorControl]:
        """Return the generator control when this node drives a generator."""
        return [self._generator] if self._generator is not None else []

    @property
    def generator(self) -> Optional[GeneratorControl]:
        return self._generator

    def process_message(self, msg: Any):
        """Process an incoming CAN message by checking all configured sensors."""
        for sensor in self._sensors:
            sensor.process_message(msg)
        if self._generator is not None:
            self._generator.process_message(msg)

    def restore_from_state(self, state: Dict[str, Any]) -> None:
        """Restore sensor values from persisted state."""
        for sensor in self.get_sensors():
            sensor_key = sensor.entity_id
            if sensor_key in state:
                sensor.value = state[sensor_key]
                self.logger.debug(f"Restored {sensor.name} = {sensor.value}")

    def store_to_state(self) -> Dict[str, Any]:
        """Store current sensor values for persistence."""
        state = {}
        for sensor in self.get_sensors():
            if sensor.value is not None:
                state[sensor.entity_id] = sensor.value
        return state
