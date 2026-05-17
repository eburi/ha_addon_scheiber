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


def test_load_editor_state_returns_missing_for_absent_file(tmp_path):
    config_path = tmp_path / "missing.yaml"
    state = load_editor_state(str(config_path))

    assert state["status"] == "missing"
    assert state["config"]["devices"] == []
