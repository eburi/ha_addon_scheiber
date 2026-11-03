"""Configuration handling for the SourceSelector ``generator`` section."""

import pytest

from scheiber.config import (
    ConfigValidationError,
    editor_to_runtime_config,
    runtime_to_editor_config,
    validate_editor_config,
)


def source_selector_device(**generator):
    device = {
        "type": "source_selector",
        "bus_id": 1,
        "name": "Generator interface",
        "sensors": [],
    }
    if generator:
        device["generator"] = generator
    return device


def test_validate_accepts_generator_section():
    normalized, warnings = validate_editor_config(
        {
            "schema_version": 1,
            "devices": [
                source_selector_device(name="Generator", entity_id="generator")
            ],
        }
    )

    assert warnings == []
    assert normalized["devices"][0]["generator"] == {
        "name": "Generator",
        "entity_id": "generator",
    }


def test_validate_defaults_generator_name():
    normalized, _ = validate_editor_config(
        {"schema_version": 1, "devices": [source_selector_device(entity_id="genset")]}
    )
    assert normalized["devices"][0]["generator"] == {
        "name": "Generator",
        "entity_id": "genset",
    }


def test_validate_omits_generator_key_when_absent():
    normalized, _ = validate_editor_config(
        {"schema_version": 1, "devices": [source_selector_device()]}
    )
    assert "generator" not in normalized["devices"][0]


def test_validate_requires_entity_id():
    with pytest.raises(ConfigValidationError) as excinfo:
        validate_editor_config(
            {
                "schema_version": 1,
                "devices": [source_selector_device(name="Generator")],
            }
        )
    assert excinfo.value.errors[0]["code"] == "missing_entity_id"


def test_validate_rejects_domain_prefix_and_bad_characters():
    with pytest.raises(ConfigValidationError) as excinfo:
        validate_editor_config(
            {
                "schema_version": 1,
                "devices": [source_selector_device(entity_id="switch.generator")],
            }
        )
    assert excinfo.value.errors[0]["code"] == "entity_id_with_domain"

    with pytest.raises(ConfigValidationError) as excinfo:
        validate_editor_config(
            {
                "schema_version": 1,
                "devices": [source_selector_device(entity_id="Gen-Set")],
            }
        )
    assert excinfo.value.errors[0]["code"] == "invalid_entity_id"


def test_validate_rejects_generator_on_bloc7():
    with pytest.raises(ConfigValidationError) as excinfo:
        validate_editor_config(
            {
                "schema_version": 1,
                "devices": [
                    {
                        "type": "bloc7",
                        "bus_id": 2,
                        "sensors": [],
                        "generator": {"entity_id": "generator"},
                    }
                ],
            }
        )
    assert excinfo.value.errors[0]["code"] == "generator_not_supported"


def test_validate_reserves_derived_entity_ids():
    """A Bloc9 output must not reuse an id the bridge derives from the generator."""
    with pytest.raises(ConfigValidationError) as excinfo:
        validate_editor_config(
            {
                "schema_version": 1,
                "devices": [
                    {
                        "type": "bloc9",
                        "bus_id": 2,
                        "outputs": {
                            "s1": {
                                "enabled": True,
                                "role": "switch",
                                "name": "Clash",
                                "entity_id": "generator_running",
                            }
                        },
                    },
                    source_selector_device(entity_id="generator"),
                ],
            }
        )
    codes = {error["code"] for error in excinfo.value.errors}
    assert "duplicate_entity_id" in codes


def test_round_trip_runtime_editor_runtime_keeps_generator():
    runtime = {
        "devices": [
            {
                "type": "source_selector",
                "bus_id": 1,
                "name": "Generator interface",
                "generator": {"name": "Generator", "entity_id": "generator"},
            }
        ]
    }
    editor = runtime_to_editor_config(runtime)
    assert editor["devices"][0]["generator"] == {
        "name": "Generator",
        "entity_id": "generator",
    }
    normalized, _ = validate_editor_config(editor)
    back = editor_to_runtime_config(normalized)
    assert back["devices"][0]["generator"] == {
        "name": "Generator",
        "entity_id": "generator",
    }
    assert back["devices"][0]["type"] == "source_selector"


def test_round_trip_without_generator_has_no_key():
    runtime = {"devices": [{"type": "source_selector", "bus_id": 1, "sensors": []}]}
    normalized, _ = validate_editor_config(runtime_to_editor_config(runtime))
    back = editor_to_runtime_config(normalized)
    assert "generator" not in back["devices"][0]
