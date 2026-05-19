from unittest.mock import MagicMock

from scheiber.bloc7 import Bloc7Device


def test_bloc7_device_builds_matcher_from_runtime_sensor_config():
    device = Bloc7Device(
        device_id=21,
        can_bus=MagicMock(),
        config={
            "sensors": [
                {
                    "sensor_type": "level",
                    "name": "Fresh water",
                    "entity_id": "fresh_water",
                    "matcher": {"pattern": 0x02040582, "mask": 0xFFFFFFFF},
                    "value_config": {
                        "start_byte": 1,
                        "bit_length": 8,
                        "endian": "little",
                        "scale": 1.0,
                    },
                }
            ]
        },
    )

    sensors = device.get_sensors()

    assert len(sensors) == 1
    assert sensors[0].name == "Fresh water"
    assert sensors[0].entity_id == "fresh_water"
    assert sensors[0].matcher.pattern == 0x02040582
    assert sensors[0].matcher.mask == 0xFFFFFFFF
    assert sensors[0].value_config.start_byte == 1
    assert sensors[0].value_config.bit_length == 8
    assert sensors[0].value_config.endian == "little"
    assert sensors[0].value_config.scale == 1.0
    assert sensors[0].unit_of_measurement == "%"
    assert sensors[0].device_class is None
    assert sensors[0].icon == "mdi:water-percent"
