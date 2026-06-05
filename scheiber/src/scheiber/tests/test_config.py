import pytest

from scheiber.config import (
    ConfigRevisionConflictError,
    ConfigValidationError,
    compute_revision,
    load_editor_state,
    runtime_to_editor_config,
    save_editor_config,
    validate_editor_config,
)


def test_runtime_to_editor_config_converts_bloc9_sections():
    runtime_config = {
        "devices": [
            {
                "type": "bloc9",
                "bus_id": 7,
                "name": "Panel 7",
                "lights": {
                    "s1": {"name": "Main light", "entity_id": "main_light"},
                },
                "switches": {
                    "s6": {"name": "Fan", "entity_id": "fan_switch"},
                },
            }
        ]
    }

    editor_config = runtime_to_editor_config(runtime_config)
    normalized, warnings = validate_editor_config(editor_config)

    assert warnings == []
    assert normalized["devices"][0]["outputs"]["s1"]["role"] == "light"
    assert normalized["devices"][0]["outputs"]["s1"]["entity_id"] == "main_light"
    assert normalized["devices"][0]["outputs"]["s6"]["role"] == "switch"
    assert normalized["devices"][0]["outputs"]["s6"]["entity_id"] == "fan_switch"
    assert normalized["devices"][0]["segment_id"] == 0


def test_runtime_to_editor_config_reads_segment_id():
    runtime_config = {
        "devices": [
            {
                "type": "bloc9",
                "bus_id": 7,
                "segment_id": 3,
                "lights": {
                    "s1": {"name": "Main light", "entity_id": "main_light"},
                },
            }
        ]
    }

    editor_config = runtime_to_editor_config(runtime_config)
    normalized, warnings = validate_editor_config(editor_config)

    assert warnings == []
    assert normalized["devices"][0]["segment_id"] == 3


def test_runtime_to_editor_config_converts_bloc7_sensor_list():
    runtime_config = {
        "devices": [
            {
                "type": "bloc7",
                "bus_id": 21,
                "name": "Tank sender bank",
                "sensors": [
                    {
                        "sensor_type": "level",
                        "name": "Black water 1",
                        "entity_id": "black_water_1",
                        "matcher": {"pattern": 0x0204058A, "mask": 0xFFFFFFFF},
                        "value_config": {
                            "start_byte": 3,
                            "bit_length": 8,
                            "endian": "little",
                            "scale": 1.0,
                        },
                    }
                ],
            }
        ]
    }

    editor_config = runtime_to_editor_config(runtime_config)
    normalized, warnings = validate_editor_config(editor_config)

    assert warnings == []
    assert normalized["devices"][0]["type"] == "bloc7"
    assert normalized["devices"][0]["sensors"][0]["matcher"]["pattern"] == 0x0204058A
    assert normalized["devices"][0]["sensors"][0]["value_config"]["start_byte"] == 3


def test_runtime_to_editor_config_converts_legacy_bloc7_sections():
    runtime_config = {
        "devices": [
            {
                "type": "bloc7",
                "bus_id": 22,
                "voltages": [
                    {
                        "name": "Generator port",
                        "entity_id": "generator_port",
                        "matcher": {"pattern": 0x02040B9A, "mask": 0xFFFFFFFF},
                        "value_config": {
                            "start_byte": 1,
                            "bit_length": 8,
                            "endian": "little",
                            "scale": 0.1,
                        },
                    }
                ],
            }
        ]
    }

    editor_config = runtime_to_editor_config(runtime_config)
    normalized, warnings = validate_editor_config(editor_config)

    assert warnings == []
    assert normalized["devices"][0]["sensors"][0]["sensor_type"] == "voltage"
    assert normalized["devices"][0]["sensors"][0]["entity_id"] == "generator_port"


def test_runtime_to_editor_config_preserves_unassigned_output_names():
    runtime_config = {
        "devices": [
            {
                "type": "bloc9",
                "bus_id": 7,
                "outputs": {
                    "s2": {"name": "Future light"},
                },
            }
        ]
    }

    editor_config = runtime_to_editor_config(runtime_config)
    normalized, warnings = validate_editor_config(editor_config)

    assert warnings == []
    assert normalized["devices"][0]["outputs"]["s2"] == {
        "enabled": False,
        "role": None,
        "name": "Future light",
        "entity_id": "",
        "initial_brightness": None,
    }


def test_validate_editor_config_allows_named_disabled_outputs():
    config = {
        "schema_version": 1,
        "devices": [
            {
                "type": "bloc9",
                "bus_id": 11,
                "name": "Panel",
                "outputs": {
                    "s4": {
                        "enabled": False,
                        "role": None,
                        "name": "Spare output",
                        "entity_id": "",
                        "initial_brightness": None,
                    }
                },
            }
        ],
    }

    normalized, warnings = validate_editor_config(config)

    assert warnings == []
    assert normalized["devices"][0]["outputs"]["s4"]["name"] == "Spare output"
    assert normalized["devices"][0]["outputs"]["s4"]["enabled"] is False


def test_validate_editor_config_allows_same_bus_id_on_different_segments():
    config = {
        "schema_version": 1,
        "devices": [
            {
                "type": "bloc9",
                "bus_id": 3,
                "segment_id": 0,
                "outputs": {
                    "s1": {
                        "enabled": True,
                        "role": "light",
                        "name": "Main",
                        "entity_id": "main_light",
                        "initial_brightness": None,
                    }
                },
            },
            {
                "type": "bloc9",
                "bus_id": 3,
                "segment_id": 2,
                "outputs": {
                    "s1": {
                        "enabled": True,
                        "role": "light",
                        "name": "Guest",
                        "entity_id": "guest_light",
                        "initial_brightness": None,
                    }
                },
            },
        ],
    }

    normalized, warnings = validate_editor_config(config)

    assert warnings == []
    assert [device["segment_id"] for device in normalized["devices"]] == [0, 2]


def test_validate_editor_config_rejects_duplicate_entity_id():
    config = {
        "schema_version": 1,
        "devices": [
            {
                "type": "bloc9",
                "bus_id": 1,
                "outputs": {
                    "s1": {
                        "enabled": True,
                        "role": "light",
                        "name": "Main",
                        "entity_id": "duplicate_entity",
                    }
                },
            },
            {
                "type": "bloc9",
                "bus_id": 2,
                "outputs": {
                    "s2": {
                        "enabled": True,
                        "role": "switch",
                        "name": "Pump",
                        "entity_id": "duplicate_entity",
                    }
                },
            },
        ],
    }

    with pytest.raises(ConfigValidationError) as exc:
        validate_editor_config(config)

    assert any(error["code"] == "duplicate_entity_id" for error in exc.value.errors)


def test_validate_editor_config_allows_shared_logical_light_entity_id():
    normalized, warnings = validate_editor_config(
        {
            "schema_version": 1,
            "devices": [
                {
                    "type": "bloc9",
                    "bus_id": 1,
                    "outputs": {
                        "s1": {
                            "enabled": True,
                            "role": "light",
                            "name": "Underwater light port",
                            "entity_id": "underwater_light",
                            "initial_brightness": None,
                        }
                    },
                },
                {
                    "type": "bloc9",
                    "bus_id": 2,
                    "outputs": {
                        "s2": {
                            "enabled": True,
                            "role": "light",
                            "name": "Underwater light starboard",
                            "entity_id": "underwater_light",
                            "initial_brightness": None,
                        }
                    },
                },
            ],
        }
    )

    assert warnings == []
    assert normalized["devices"][0]["outputs"]["s1"]["entity_id"] == "underwater_light"
    assert normalized["devices"][1]["outputs"]["s2"]["entity_id"] == "underwater_light"


def test_validate_editor_config_rejects_shared_entity_id_across_roles():
    with pytest.raises(ConfigValidationError) as exc:
        validate_editor_config(
            {
                "schema_version": 1,
                "devices": [
                    {
                        "type": "bloc9",
                        "bus_id": 1,
                        "outputs": {
                            "s1": {
                                "enabled": True,
                                "role": "light",
                                "name": "Main light",
                                "entity_id": "shared_entity",
                                "initial_brightness": None,
                            }
                        },
                    },
                    {
                        "type": "bloc9",
                        "bus_id": 2,
                        "outputs": {
                            "s1": {
                                "enabled": True,
                                "role": "switch",
                                "name": "Shared switch",
                                "entity_id": "shared_entity",
                                "initial_brightness": None,
                            }
                        },
                    },
                ],
            }
        )

    assert any(error["code"] == "duplicate_entity_id" for error in exc.value.errors)


def test_validate_editor_config_accepts_bloc7_sensor_strings():
    config = {
        "schema_version": 1,
        "devices": [
            {
                "type": "bloc7",
                "bus_id": 30,
                "name": "Tank bank",
                "segment_id": 0,
                "sensors": [
                    {
                        "name": "Black water 1",
                        "entity_id": "black_water_1",
                        "sensor_type": "level",
                        "matcher": {
                            "pattern": "0x0204058A",
                            "mask": "0xFFFFFFFF",
                        },
                        "value_config": {
                            "start_byte": "3",
                            "bit_length": "8",
                            "endian": "little",
                            "scale": "1.0",
                        },
                    }
                ],
            }
        ],
    }

    normalized, warnings = validate_editor_config(config)

    assert warnings == []
    sensor = normalized["devices"][0]["sensors"][0]
    assert sensor["matcher"]["pattern"] == 0x0204058A
    assert sensor["matcher"]["mask"] == 0xFFFFFFFF
    assert sensor["value_config"]["start_byte"] == 3
    assert sensor["value_config"]["scale"] == 1.0


def test_validate_editor_config_accepts_bloc7_segment_id():
    normalized, warnings = validate_editor_config(
        {
            "schema_version": 1,
            "devices": [
                {
                    "type": "bloc7",
                    "bus_id": 1,
                    "segment_id": 2,
                    "sensors": [
                        {
                            "name": "Tank",
                            "entity_id": "tank",
                            "sensor_type": "level",
                            "matcher": {
                                "pattern": 0x0204058A,
                                "mask": 0xFFFFFFFF,
                            },
                            "value_config": {
                                "start_byte": 1,
                                "bit_length": 8,
                                "endian": "little",
                                "scale": 1.0,
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert warnings == []
    assert normalized["devices"][0]["segment_id"] == 2


def test_validate_editor_config_accepts_source_selector_sensors():
    normalized, warnings = validate_editor_config(
        {
            "schema_version": 1,
            "devices": [
                {
                    "type": "source_selector",
                    "bus_id": 3,
                    "segment_id": 2,
                    "name": "AC selector",
                    "sensors": [
                        {
                            "name": "Generator voltage",
                            "entity_id": "generator_voltage",
                            "sensor_type": "voltage",
                            "matcher": {
                                "pattern": 0x02040B9A,
                                "mask": 0xFFFFFFFF,
                            },
                            "value_config": {
                                "start_byte": 5,
                                "bit_length": 8,
                                "endian": "little",
                                "scale": 1.0,
                            },
                        },
                        {
                            "name": "Generator frequency",
                            "entity_id": "generator_frequency",
                            "sensor_type": "frequency",
                            "matcher": {
                                "pattern": 0x02040B9A,
                                "mask": 0xFFFFFFFF,
                            },
                            "value_config": {
                                "start_byte": 7,
                                "bit_length": 8,
                                "endian": "little",
                                "scale": 1.0,
                            },
                        },
                    ],
                }
            ],
        }
    )

    assert warnings == []
    assert normalized["devices"][0]["type"] == "source_selector"
    assert normalized["devices"][0]["sensors"][1]["sensor_type"] == "frequency"


def test_save_editor_config_writes_and_enforces_revision(tmp_path):
    config_path = tmp_path / "scheiber-config.yaml"
    config = {
        "schema_version": 1,
        "devices": [
            {
                "type": "bloc9",
                "bus_id": 7,
                "name": "Panel",
                "description": "Cabin lights",
                "outputs": {
                    "s1": {
                        "enabled": True,
                        "role": "light",
                        "name": "Main",
                        "entity_id": "main_light",
                        "initial_brightness": 120,
                    }
                },
            }
        ],
    }

    first_save = save_editor_config(str(config_path), config)

    assert config_path.exists()
    saved_state = load_editor_state(str(config_path))
    assert saved_state["status"] == "valid"
    assert saved_state["config"]["devices"][0]["bus_id"] == 7

    with pytest.raises(ConfigRevisionConflictError):
        save_editor_config(
            str(config_path),
            config,
            expected_revision=compute_revision("outdated"),
        )

    second_save = save_editor_config(
        str(config_path),
        config,
        expected_revision=first_save["revision"],
    )
    assert second_save["revision"] == first_save["revision"]


def test_save_editor_config_omits_segment_id_for_native_segment(tmp_path):
    config_path = tmp_path / "scheiber-config.yaml"
    config = {
        "schema_version": 1,
        "devices": [
            {
                "type": "bloc9",
                "bus_id": 7,
                "segment_id": 0,
                "outputs": {
                    "s1": {
                        "enabled": True,
                        "role": "light",
                        "name": "Main",
                        "entity_id": "main_light",
                        "initial_brightness": None,
                    }
                },
            }
        ],
    }

    save_editor_config(str(config_path), config)

    saved_text = config_path.read_text(encoding="utf-8")
    assert "segment_id" not in saved_text


def test_save_editor_config_persists_nonzero_segment_id(tmp_path):
    config_path = tmp_path / "scheiber-config.yaml"
    config = {
        "schema_version": 1,
        "devices": [
            {
                "type": "bloc9",
                "bus_id": 7,
                "segment_id": 3,
                "outputs": {
                    "s1": {
                        "enabled": True,
                        "role": "light",
                        "name": "Main",
                        "entity_id": "main_light",
                        "initial_brightness": None,
                    }
                },
            }
        ],
    }

    save_editor_config(str(config_path), config)

    saved_text = config_path.read_text(encoding="utf-8")
    assert "segment_id: 3" in saved_text


def test_save_editor_config_persists_output_metadata_for_disabled_outputs(tmp_path):
    config_path = tmp_path / "scheiber-config.yaml"
    config = {
        "schema_version": 1,
        "devices": [
            {
                "type": "bloc9",
                "bus_id": 9,
                "name": "Panel",
                "description": "Cabin",
                "outputs": {
                    "s1": {
                        "enabled": True,
                        "role": "light",
                        "name": "Main light",
                        "entity_id": "main_light",
                        "initial_brightness": None,
                    },
                    "s2": {
                        "enabled": False,
                        "role": None,
                        "name": "Unused reading light",
                        "entity_id": "",
                        "initial_brightness": None,
                    },
                },
            }
        ],
    }

    save_editor_config(str(config_path), config)

    saved_text = config_path.read_text(encoding="utf-8")
    assert "outputs:" in saved_text
    assert "Unused reading light" in saved_text
    assert "lights:" in saved_text
    assert "main_light" in saved_text

    state = load_editor_state(str(config_path))
    assert (
        state["config"]["devices"][0]["outputs"]["s2"]["name"] == "Unused reading light"
    )
    assert state["config"]["devices"][0]["outputs"]["s2"]["enabled"] is False


def test_save_editor_config_persists_bloc7_sensors(tmp_path):
    config_path = tmp_path / "scheiber-config.yaml"
    config = {
        "schema_version": 1,
        "devices": [
            {
                "type": "bloc7",
                "bus_id": 31,
                "name": "Tank bank",
                "description": "Manual matcher config",
                "sensors": [
                    {
                        "name": "Black water 2",
                        "entity_id": "black_water_2",
                        "sensor_type": "level",
                        "matcher": {
                            "pattern": 0x0204058B,
                            "mask": 0xFFFFFFFF,
                        },
                        "value_config": {
                            "start_byte": 1,
                            "bit_length": 8,
                            "endian": "little",
                            "scale": 1.0,
                        },
                    }
                ],
            }
        ],
    }

    save_editor_config(str(config_path), config)

    saved_text = config_path.read_text(encoding="utf-8")
    assert "type: bloc7" in saved_text
    assert "sensor_type: level" in saved_text
    assert "black_water_2" in saved_text

    state = load_editor_state(str(config_path))
    assert state["config"]["devices"][0]["type"] == "bloc7"
    assert state["config"]["devices"][0]["sensors"][0]["entity_id"] == "black_water_2"


def test_load_editor_state_returns_missing_for_absent_file(tmp_path):
    config_path = tmp_path / "missing.yaml"
    state = load_editor_state(str(config_path))

    assert state["status"] == "missing"
    assert state["config"]["devices"] == []
