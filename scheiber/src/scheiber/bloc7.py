"""
Scheiber Bloc7 Device.

Represents a Bloc7 device that reports sensor values like voltages and tank levels,
driven by a configuration file.
"""

import logging
from typing import Any, Dict, List

from .base_device import ScheiberCanDevice
from .matchers import Matcher
from .output import Output

logger = logging.getLogger(__name__)


class ValueConfig:
    """Configuration for extracting a value from a CAN message."""

    def __init__(self, start_byte: int, bit_length: int, endian: str, scale: float):
        self.start_byte = start_byte
        self.bit_length = bit_length
        self.endian = endian
        self.scale = scale

    def extract_value(self, data: bytes) -> float:
        """Extracts and scales the value from the CAN data payload."""
        num_bytes = (self.bit_length + 7) // 8
        end_byte = self.start_byte + num_bytes
        if end_byte > len(data):
            logger.warning(
                f"Not enough data to extract value. Need {end_byte} bytes, have {len(data)}."
            )
            return 0.0

        byte_slice = data[self.start_byte : end_byte]

        if self.endian == "little":
            raw_value = int.from_bytes(byte_slice, "little")
        else:
            raw_value = int.from_bytes(byte_slice, "big")

        return round(raw_value * self.scale, 2)


class SensorOutput(Output):
    """Base class for a sensor output (e.g., Voltage, Level)."""

    def __init__(
        self,
        name: str,
        entity_id: str,
        matcher: Matcher,
        value_config: ValueConfig,
        unit: str,
    ):
        super().__init__(name, matcher)
        self.entity_id = entity_id
        self.value_config = value_config
        self.unit_of_measurement = unit
        self.value = None
        self.observers: List[Any] = []
        self.device_class = None
        self.icon = None

    def process_message(self, msg: Any) -> bool:
        """Process a CAN message and update the sensor value if it matches."""
        if self.matcher.matches(msg):
            new_value = self.value_config.extract_value(msg.data)
            if self.value != new_value:
                self.value = new_value
                logger.info(
                    f"Sensor '{self.name}' updated to {self.value} {self.unit_of_measurement}"
                )
                self.notify_observers()
                return True
        return False

    def get_value(self):
        """Get current sensor value."""
        return self.value

    def subscribe(self, callback):
        if callback not in self.observers:
            self.observers.append(callback)

    def notify_observers(self):
        for callback in self.observers:
            callback({"value": self.value})


class Voltage(SensorOutput):
    """Represents a voltage sensor."""

    def __init__(
        self, name: str, entity_id: str, matcher: Matcher, value_config: ValueConfig
    ):
        super().__init__(name, entity_id, matcher, value_config, "V")
        self.type = "voltage"
        self.device_class = "voltage"


class Level(SensorOutput):
    """Represents a tank level sensor."""

    def __init__(
        self, name: str, entity_id: str, matcher: Matcher, value_config: ValueConfig
    ):
        super().__init__(name, entity_id, matcher, value_config, "L")
        self.type = "level"
        self.device_class = "volume"


class Bloc7Device(ScheiberCanDevice):
    """
    Represents a Scheiber Bloc7 for monitoring analog inputs.
    This device is configured from a dictionary, creating Voltage and Level sensors.
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
            device_id, "bloc7", can_bus, segment_id=segment_id, logger=logger
        )
        self._sensors: List[SensorOutput] = []

        runtime_sensors = config.get("sensors")
        if runtime_sensors is None:
            runtime_sensors = []
            for sensor_type, section_name in (
                ("voltage", "voltages"),
                ("level", "levels"),
            ):
                for sensor_config in config.get(section_name, []):
                    runtime_sensors.append(
                        {
                            "sensor_type": sensor_type,
                            **sensor_config,
                        }
                    )

        for sensor_config in runtime_sensors:
            matcher = Matcher(sensor_config["matcher"])
            value_config = ValueConfig(**sensor_config["value_config"])
            entity_id = sensor_config.get(
                "entity_id", sensor_config["name"].lower().replace(" ", "_")
            )
            sensor_type = sensor_config.get("sensor_type", "level")
            if sensor_type == "voltage":
                self._sensors.append(
                    Voltage(sensor_config["name"], entity_id, matcher, value_config)
                )
            elif sensor_type == "level":
                self._sensors.append(
                    Level(sensor_config["name"], entity_id, matcher, value_config)
                )
            else:
                raise ValueError(f"Unsupported Bloc7 sensor_type: {sensor_type}")

    def get_matchers(self) -> List[Matcher]:
        """Return all matchers from configured sensors."""
        return [sensor.matcher for sensor in self._sensors]

    def get_sensors(self) -> List[SensorOutput]:
        """Return a list of all sensor objects associated with this device."""
        return self._sensors

    def process_message(self, msg: Any):
        """
        Process an incoming CAN message by checking it against all configured sensors.
        """
        for sensor in self._sensors:
            sensor.process_message(msg)

    def restore_from_state(self, state: Dict[str, Any]) -> None:
        """Restore sensor values from persisted state."""
        for sensor in self._sensors:
            sensor_key = sensor.name.lower().replace(" ", "_")
            if sensor_key in state:
                sensor.value = state[sensor_key]
                self.logger.debug(f"Restored {sensor.name} = {sensor.value}")

    def store_to_state(self) -> Dict[str, Any]:
        """Store current sensor values for persistence."""
        state = {}
        for sensor in self._sensors:
            sensor_key = sensor.name.lower().replace(" ", "_")
            if sensor.value is not None:
                state[sensor_key] = sensor.value
        return state
