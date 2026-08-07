"""Read-only Scheiber SourceSelector monitoring device."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base_device import ScheiberCanDevice
from .bloc7 import SENSOR_TYPES, SensorOutput, ValueConfig, create_sensor_output
from .matchers import Matcher

logger = logging.getLogger(__name__)


class SourceSelectorDevice(ScheiberCanDevice):
    """Read-only SourceSelector sensor container.

    Source selectors switch high-power AC sources. This class intentionally
    exposes measurements only and has no command-sending API.
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

    def get_matchers(self) -> List[Matcher]:
        """Return all matchers from configured sensors."""
        return [sensor.matcher for sensor in self._sensors]

    def get_sensors(self) -> List[SensorOutput]:
        """Return configured read-only measurement sensors."""
        return self._sensors

    def process_message(self, msg: Any):
        """Process an incoming CAN message by checking all configured sensors."""
        for sensor in self._sensors:
            sensor.process_message(msg)

    def restore_from_state(self, state: Dict[str, Any]) -> None:
        """Restore sensor values from persisted state."""
        for sensor in self._sensors:
            sensor_key = sensor.entity_id
            if sensor_key in state:
                sensor.value = state[sensor_key]
                self.logger.debug(f"Restored {sensor.name} = {sensor.value}")

    def store_to_state(self) -> Dict[str, Any]:
        """Store current sensor values for persistence."""
        state = {}
        for sensor in self._sensors:
            if sensor.value is not None:
                state[sensor.entity_id] = sensor.value
        return state
