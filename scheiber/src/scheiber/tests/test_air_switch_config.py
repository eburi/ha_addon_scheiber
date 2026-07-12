"""Tests for air_switch device configuration schema/validation."""

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
                "bus_id": 1,
                "name": "Bow Salon Air Switch",
                "description": "4-button Air Switch at the bow salon door",
                "buttons": [
                    {
                        "name": "Bottom Left",
                        "entity_id": "bow_salon_bottom_left",
                        "identity": "52AB81",
                        "button_index": 1,
                    },
                    {
                        "name": "Top Left",
                        "entity_id": "bow_salon_top_left",
                        "identity": "52AB81",
                        "button_index": 2,
                    },
                ],
            }
        ],
    }


def test_validate_editor_config_accepts_air_switch_buttons():
    normalized, warnings = validate_editor_config(_valid_air_switch_config())

    assert warnings == []
    device = normalized["devices"][0]
    assert device["type"] == "air_switch"
    assert len(device["buttons"]) == 2
    assert device["buttons"][0]["identity"] == "52AB81"
    assert device["buttons"][1]["button_index"] == 2


def test_validate_editor_config_normalizes_identity_case():
    config = _valid_air_switch_config()
    config["devices"][0]["buttons"][0]["identity"] = "52ab81"

    normalized, _warnings = validate_editor_config(config)

    assert normalized["devices"][0]["buttons"][0]["identity"] == "52AB81"


@pytest.mark.parametrize(
    "mutation,expected_code",
    [
        (lambda button: button.update(name=""), "missing_button_name"),
        (lambda button: button.update(entity_id=""), "missing_entity_id"),
        (lambda button: button.update(entity_id="event.foo"), "entity_id_with_domain"),
        (lambda button: button.update(entity_id="Not Valid"), "invalid_entity_id"),
        (lambda button: button.update(identity="XYZ"), "invalid_air_switch_identity"),
        (lambda button: button.update(identity="52AB8"), "invalid_air_switch_identity"),
        (lambda button: button.update(button_index=0), "invalid_button_index"),
        (lambda button: button.update(button_index=9), "invalid_button_index"),
        (
            lambda button: button.update(button_index="not-a-number"),
            "invalid_button_index",
        ),
    ],
)
def test_validate_editor_config_rejects_invalid_button_fields(mutation, expected_code):
    config = _valid_air_switch_config()
    mutation(config["devices"][0]["buttons"][0])

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_editor_config(config)

    codes = {error["code"] for error in exc_info.value.errors}
    assert expected_code in codes


def test_validate_editor_config_rejects_duplicate_entity_id_across_buttons():
    config = _valid_air_switch_config()
    config["devices"][0]["buttons"][1]["entity_id"] = "bow_salon_bottom_left"

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_editor_config(config)

    assert any(
        error["code"] == "duplicate_entity_id" for error in exc_info.value.errors
    )


def test_validate_editor_config_rejects_duplicate_identity_and_button_index():
    config = _valid_air_switch_config()
    config["devices"][0]["buttons"][1]["identity"] = "52AB81"
    config["devices"][0]["buttons"][1]["button_index"] = 1

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_editor_config(config)

    assert any(
        error["code"] == "duplicate_air_switch_button"
        for error in exc_info.value.errors
    )


def test_validate_editor_config_rejects_duplicate_button_across_devices():
    config = _valid_air_switch_config()
    config["devices"].append(
        {
            "type": "air_switch",
            "bus_id": 2,
            "name": "Duplicate group",
            "buttons": [
                {
                    "name": "Duplicate",
                    "entity_id": "some_other_entity",
                    "identity": "52AB81",
                    "button_index": 1,
                }
            ],
        }
    )

    with pytest.raises(ConfigValidationError) as exc_info:
        validate_editor_config(config)

    assert any(
        error["code"] == "duplicate_air_switch_button"
        for error in exc_info.value.errors
    )


def test_validate_editor_config_allows_same_button_index_different_identity():
    config = _valid_air_switch_config()
    config["devices"][0]["buttons"][1]["identity"] = "AABBCC"
    config["devices"][0]["buttons"][1]["button_index"] = 1

    normalized, warnings = validate_editor_config(config)

    assert warnings == []
    assert len(normalized["devices"][0]["buttons"]) == 2


def test_runtime_to_editor_config_converts_air_switch_buttons():
    runtime_config = {
        "devices": [
            {
                "type": "air_switch",
                "bus_id": 1,
                "name": "Bow Salon Air Switch",
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
    assert normalized["devices"][0]["type"] == "air_switch"
    assert normalized["devices"][0]["buttons"][0]["identity"] == "52AB81"


def test_editor_to_runtime_config_round_trips_air_switch_buttons():
    normalized, _warnings = validate_editor_config(_valid_air_switch_config())

    runtime_config = editor_to_runtime_config(normalized)

    device = next(d for d in runtime_config["devices"] if d["type"] == "air_switch")
    assert device["buttons"] == [
        {
            "name": "Bottom Left",
            "entity_id": "bow_salon_bottom_left",
            "identity": "52AB81",
            "button_index": 1,
        },
        {
            "name": "Top Left",
            "entity_id": "bow_salon_top_left",
            "identity": "52AB81",
            "button_index": 2,
        },
    ]


def test_save_editor_config_persists_air_switch_buttons(tmp_path):
    config_path = tmp_path / "scheiber-config.yaml"
    normalized, _warnings = validate_editor_config(_valid_air_switch_config())

    result = save_editor_config(str(config_path), normalized)

    assert "buttons:" in result["raw_yaml"]
    assert (
        "identity: 52AB81" in result["raw_yaml"]
        or "identity: '52AB81'" in result["raw_yaml"]
    )
