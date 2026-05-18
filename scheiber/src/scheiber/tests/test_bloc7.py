from unittest.mock import MagicMock

import scheiber.bloc7 as bloc7_module


def test_bloc7_device_builds_matcher_from_runtime_sensor_config(monkeypatch):
    captured = {}

    class FakeMatcher:
        def __init__(self, pattern, mask):
            captured["pattern"] = pattern
            captured["mask"] = mask

    class FakeLevel:
        def __init__(self, name, entity_id, matcher, value_config):
            self.name = name
            self.entity_id = entity_id
            self.matcher = matcher
            self.value_config = value_config

    monkeypatch.setattr(bloc7_module, "Matcher", FakeMatcher)
    monkeypatch.setattr(bloc7_module, "Level", FakeLevel)

    device = bloc7_module.Bloc7Device(
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

    assert captured == {"pattern": 0x02040582, "mask": 0xFFFFFFFF}
    assert len(sensors) == 1
    assert sensors[0].entity_id == "fresh_water"
    assert sensors[0].value_config.start_byte == 1
    assert sensors[0].value_config.bit_length == 8
    assert sensors[0].value_config.endian == "little"
    assert sensors[0].value_config.scale == 1.0
