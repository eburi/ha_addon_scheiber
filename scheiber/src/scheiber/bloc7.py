"""
Scheiber Bloc7 Device.

Represents a Bloc7 device that reports sensor values like voltages and tank levels,
driven by a configuration file.
"""

import logging
from typing import Any, Dict, List

from .base_device import ScheiberCanDevice
from .matchers import Matcher

logger = logging.getLogger(__name__)

SENSOR_TYPES = {"voltage", "level", "frequency", "current", "state_of_charge", "raw"}


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


class SensorOutput:
    """Base class for a sensor output (e.g., Voltage, Level)."""

    def __init__(
        self,
        name: str,
        entity_id: str,
        matcher: Matcher,
        value_config: ValueConfig,
        unit: str,
    ):
        self.name = name
        self.entity_id = entity_id
        self.matcher = matcher
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


class Frequency(SensorOutput):
    """Represents an AC frequency sensor."""

    def __init__(
        self, name: str, entity_id: str, matcher: Matcher, value_config: ValueConfig
    ):
        super().__init__(name, entity_id, matcher, value_config, "Hz")
        self.type = "frequency"
        self.device_class = "frequency"


class Current(SensorOutput):
    """Represents a current sensor."""

    def __init__(
        self, name: str, entity_id: str, matcher: Matcher, value_config: ValueConfig
    ):
        super().__init__(name, entity_id, matcher, value_config, "A")
        self.type = "current"
        self.device_class = "current"


class StateOfCharge(SensorOutput):
    """Represents a battery state-of-charge sensor."""

    def __init__(
        self, name: str, entity_id: str, matcher: Matcher, value_config: ValueConfig
    ):
        super().__init__(name, entity_id, matcher, value_config, "%")
        self.type = "state_of_charge"
        self.device_class = "battery"


class RawValue(SensorOutput):
    """Represents an unscaled or provisional raw sensor value."""

    def __init__(
        self, name: str, entity_id: str, matcher: Matcher, value_config: ValueConfig
    ):
        super().__init__(name, entity_id, matcher, value_config, "")
        self.type = "raw"
        self.icon = "mdi:counter"


class Level(SensorOutput):
    """Represents a tank level sensor."""

    def __init__(
        self, name: str, entity_id: str, matcher: Matcher, value_config: ValueConfig
    ):
        super().__init__(name, entity_id, matcher, value_config, "%")
        self.type = "level"
        self.icon = "mdi:water-percent"


def create_sensor_output(
    sensor_type: str,
    name: str,
    entity_id: str,
    matcher: Matcher,
    value_config: ValueConfig,
) -> SensorOutput:
    """Create a configured sensor output by sensor type."""
    sensor_classes = {
        "voltage": Voltage,
        "level": Level,
        "frequency": Frequency,
        "current": Current,
        "state_of_charge": StateOfCharge,
        "raw": RawValue,
    }
    sensor_class = sensor_classes.get(sensor_type)
    if sensor_class is None:
        raise ValueError(f"Unsupported sensor_type: {sensor_type}")
    return sensor_class(name, entity_id, matcher, value_config)


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
            matcher = Matcher(**sensor_config["matcher"])
            value_config = ValueConfig(**sensor_config["value_config"])
            entity_id = sensor_config.get(
                "entity_id", sensor_config["name"].lower().replace(" ", "_")
            )
            sensor_type = sensor_config.get("sensor_type", "level")
            if sensor_type not in SENSOR_TYPES:
                raise ValueError(f"Unsupported Bloc7 sensor_type: {sensor_type}")
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
            sensor_key = sensor.entity_id
            legacy_key = sensor.name.lower().replace(" ", "_")
            if sensor_key in state:
                sensor.value = state[sensor_key]
                self.logger.debug(f"Restored {sensor.name} = {sensor.value}")
            elif legacy_key in state:
                sensor.value = state[legacy_key]
                self.logger.debug(f"Restored legacy {sensor.name} = {sensor.value}")

    def store_to_state(self) -> Dict[str, Any]:
        """Store current sensor values for persistence."""
        state = {}
        for sensor in self._sensors:
            if sensor.value is not None:
                state[sensor.entity_id] = sensor.value
        return state
