"""Tests for v7 air_switch device configuration schema/validation."""

import pytest

from scheiber.config import (
    ConfigValidationError,
    editor_to_runtime_config,
    runtime_to_editor_config,
    save_editor_config,
    validate_editor_config,
)


def _valid_air_switch_config():
    return {
        "schema_version": 1,
        "devices": [
            {
                "type": "air_switch",
                "identity": "52AB81",
                "name": "Bow Salon AirSwitch",
                "description": "4-button AirSwitch at the bow salon door",
                "buttons": {
                    "1": {"name": "Bottom Left", "published": True},
                    "2": {"name": "Top Left", "published": False},
                },
            }
        ],
    }


def test_validate_editor_config_accepts_air_switch_buttons():
    normalized, warnings = validate_editor_config(_valid_air_switch_config())

    assert warnings == []
    device = normalized["devices"][0]
    assert device["type"] == "air_switch"
    assert device["identity"] == "52AB81"
    assert device["buttons"]["1"] == {"name": "Bottom Left", "published": True}
    assert device["buttons"]["2"] == {"name": "Top Left", "published": False}


def test_validate_editor_config_normalizes_identity_case():
    config = _valid_air_switch_config()
    config["devices"][0]["identity"] = "52ab81"

    normalized, _warnings = validate_editor_config(config)

    assert normalized["devices"][0]["identity"] == "52AB81"


@pytest.mark.parametrize(
    "mutation,expected_code",
    [
        (lambda device: device.update(identity="XYZ"), "invalid_air_switch_identity"),
        (lambda device: device.update(identity="52AB8"), "invalid_air_switch_identity"),
        (
            lambda device: device["buttons"].update({"0": {"name": "Bad"}}),
            "invalid_button_index",
        ),
        (
            lambda device: device["buttons"].update({"9": {"name": "Bad"}}),
            "invalid_button_index",
        ),
        (
            lambda device: device["buttons"].update({"x": {"name": "Bad"}}),
            "invalid_button_index",
        ),
        (lambda device: device["buttons"]["1"].update(name=123), "invalid_button_name"),
        (
            lambda device: device["buttons"]["1"].update(published="yes"),
            "invalid_published",
        ),
    ],
)
def test_validate_editor_config_rejects_invalid_air_switch_fields(
    mutation, expected_code
):
    config = _valid_air_switch_config()
    mutation(config["devices"][0])

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_editor_config(config)

    codes = {error["code"] for error in exc_info.value.errors}
    assert expected_code in codes


def test_validate_editor_config_rejects_duplicate_air_switch_identity():
    config = _valid_air_switch_config()
    config["devices"].append(
        {
            "type": "air_switch",
            "identity": "52AB81",
            "buttons": {"1": {"name": "Other", "published": True}},
        }
    )

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_editor_config(config)

    assert any(error["code"] == "duplicate_device" for error in exc_info.value.errors)


def test_validate_editor_config_accepts_entity_id_override_when_valid():
    config = _valid_air_switch_config()
    config["devices"][0]["buttons"]["1"]["entity_id"] = "bow_salon_bottom_left"

    normalized, warnings = validate_editor_config(config)

    assert warnings == []
    assert (
        normalized["devices"][0]["buttons"]["1"]["entity_id"] == "bow_salon_bottom_left"
    )


def test_runtime_to_editor_config_converts_air_switch_buttons():
    runtime_config = {
        "devices": [
            {
                "type": "air_switch",
                "identity": "52AB81",
                "name": "Bow Salon AirSwitch",
                "buttons": {"1": {"name": "Bottom Left", "published": True}},
            }
        ]
    }

    editor_config = runtime_to_editor_config(runtime_config)
    normalized, warnings = validate_editor_config(editor_config)

    assert warnings == []
    assert normalized["devices"][0]["type"] == "air_switch"
    assert normalized["devices"][0]["identity"] == "52AB81"
    assert normalized["devices"][0]["buttons"]["1"]["name"] == "Bottom Left"


def test_runtime_to_editor_config_accepts_legacy_air_switch_list_shape():
    runtime_config = {
        "devices": [
            {
                "type": "air_switch",
                "bus_id": 1,
                "name": "Legacy Bow Salon AirSwitch",
                "buttons": [
                    {
                        "name": "Bottom Left",
                        "entity_id": "bow_salon_bottom_left",
                        "identity": "52AB81",
                        "button_index": 1,
                    }
                ],
            }
        ]
    }

    editor_config = runtime_to_editor_config(runtime_config)
    normalized, warnings = validate_editor_config(editor_config)

    assert warnings == []
    assert normalized["devices"][0]["identity"] == "52AB81"
    assert normalized["devices"][0]["buttons"]["1"]["name"] == "Bottom Left"


def test_editor_to_runtime_config_round_trips_air_switch_buttons():
    normalized, _warnings = validate_editor_config(_valid_air_switch_config())

    runtime_config = editor_to_runtime_config(normalized)

    device = next(d for d in runtime_config["devices"] if d["type"] == "air_switch")
    assert "bus_id" not in device
    assert device["identity"] == "52AB81"
    assert device["buttons"] == {
        "1": {"name": "Bottom Left", "published": True},
        "2": {"name": "Top Left", "published": False},
    }


def test_save_editor_config_persists_air_switch_buttons(tmp_path):
    config_path = tmp_path / "scheiber-config.yaml"
    normalized, _warnings = validate_editor_config(_valid_air_switch_config())

    result = save_editor_config(str(config_path), normalized)

    assert (
        "identity: 52AB81" in result["raw_yaml"]
        or "identity: '52AB81'" in result["raw_yaml"]
    )
    assert "published: false" in result["raw_yaml"]
