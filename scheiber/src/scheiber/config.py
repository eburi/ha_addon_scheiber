"""
Configuration loading, validation, and atomic persistence helpers.
"""

from __future__ import annotations

import copy
import hashlib
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import yaml

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+$")
AIR_SWITCH_IDENTITY_RE = re.compile(r"^[0-9A-Fa-f]{6}$")
BLOC9_OUTPUT_KEYS = tuple(f"s{i}" for i in range(1, 7))
SENSOR_DEVICE_TYPES = {"bloc7", "source_selector"}
AIR_SWITCH_DEVICE_TYPE = "air_switch"
AIR_SWITCH_BUTTON_INDEX_MIN = 1
AIR_SWITCH_BUTTON_INDEX_MAX = 8
SUPPORTED_DEVICE_TYPES = {"bloc9", *SENSOR_DEVICE_TYPES, AIR_SWITCH_DEVICE_TYPE}
OUTPUT_METADATA_KEYS = {"name"}
BLOC7_SENSOR_TYPES = {
    "voltage",
    "level",
    "frequency",
    "current",
    "state_of_charge",
    "raw",
}
BLOC7_ENDIAN_OPTIONS = {"little", "big"}


class ConfigValidationError(ValueError):
    """Raised when configuration validation fails."""

    def __init__(
        self, errors: List[Dict[str, Any]], warnings: Optional[List[str]] = None
    ):
        self.errors = errors
        self.warnings = warnings or []
        message = "; ".join(error["message"] for error in errors)
        super().__init__(message)


class ConfigRevisionConflictError(ValueError):
    """Raised when the caller tries to save an outdated config revision."""


def empty_editor_config() -> Dict[str, Any]:
    """Return an empty editor config."""
    return {"schema_version": 1, "devices": []}


def empty_editor_output() -> Dict[str, Any]:
    """Return the default editor state for a Bloc9 output."""
    return {
        "enabled": False,
        "role": None,
        "name": "",
        "entity_id": "",
        "initial_brightness": None,
    }


def empty_editor_sensor() -> Dict[str, Any]:
    """Return the default editor state for a sensor device sensor."""
    return {
        "name": "",
        "entity_id": "",
        "sensor_type": "level",
        "matcher": {"pattern": None, "mask": None},
        "value_config": {
            "start_byte": 0,
            "bit_length": 8,
            "endian": "little",
            "scale": 1.0,
        },
    }


def empty_editor_air_switch_button() -> Dict[str, Any]:
    """Return the default editor state for a wireless Air Switch button."""
    return {
        "name": "",
        "entity_id": "",
        "identity": "",
        "button_index": AIR_SWITCH_BUTTON_INDEX_MIN,
    }


def _normalize_int_field(
    value: Any,
    code: str,
    message: str,
    path: List[Any],
    *,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    """Normalize an integer field from int or numeric string input."""
    if isinstance(value, bool):
        return None, make_error(code, message, path)

    normalized: Optional[int]
    if isinstance(value, int):
        normalized = value
    elif isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return None, make_error(code, message, path)
        try:
            normalized = int(text, 16) if text.startswith("0x") else int(text, 10)
        except ValueError:
            return None, make_error(code, message, path)
    else:
        return None, make_error(code, message, path)

    if min_value is not None and normalized < min_value:
        return None, make_error(code, message, path)
    if max_value is not None and normalized > max_value:
        return None, make_error(code, message, path)
    return normalized, None


def _normalize_float_field(
    value: Any, code: str, message: str, path: List[Any]
) -> Tuple[Optional[float], Optional[Dict[str, Any]]]:
    """Normalize a float field from numeric or string input."""
    if isinstance(value, bool):
        return None, make_error(code, message, path)
    if isinstance(value, (int, float)):
        return float(value), None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, make_error(code, message, path)
        try:
            return float(text), None
        except ValueError:
            return None, make_error(code, message, path)
    return None, make_error(code, message, path)


def compute_revision(raw_yaml: str) -> str:
    """Compute a stable revision hash for a config payload."""
    digest = hashlib.sha256(raw_yaml.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def load_runtime_config(config_path: Optional[str]) -> Dict[str, Any]:
    """
    Load and validate runtime configuration from disk.

    Args:
        config_path: Path to the YAML config file. None enables empty auto-discovery mode.

    Returns:
        Runtime configuration in the current YAML-compatible format.
    """
    if not config_path:
        return {"devices": []}

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    raw_yaml = path.read_text(encoding="utf-8")
    try:
        raw_data = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse configuration: {exc}") from exc

    editor_config = runtime_to_editor_config(raw_data)
    normalized_config, _warnings = validate_editor_config(editor_config)
    return editor_to_runtime_config(normalized_config)


def load_editor_state(config_path: str) -> Dict[str, Any]:
    """
    Load editor-friendly configuration state from disk.

    Returns a structured response suitable for the web API.
    """
    path = Path(config_path)
    if not path.exists():
        return {
            "path": config_path,
            "status": "missing",
            "revision": None,
            "raw_yaml": "",
            "config": empty_editor_config(),
            "diagnostics": {"errors": [], "warnings": []},
        }

    raw_yaml = path.read_text(encoding="utf-8")
    revision = compute_revision(raw_yaml)

    try:
        raw_data = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as exc:
        return {
            "path": config_path,
            "status": "invalid",
            "revision": revision,
            "raw_yaml": raw_yaml,
            "config": empty_editor_config(),
            "diagnostics": {
                "errors": [
                    make_error(
                        "yaml_parse_error",
                        f"Failed to parse YAML: {exc}",
                        ["raw_yaml"],
                    )
                ],
                "warnings": [],
            },
        }

    try:
        editor_config = runtime_to_editor_config(raw_data)
        normalized_config, warnings = validate_editor_config(editor_config)
    except ConfigValidationError as exc:
        return {
            "path": config_path,
            "status": "invalid",
            "revision": revision,
            "raw_yaml": raw_yaml,
            "config": empty_editor_config(),
            "diagnostics": {"errors": exc.errors, "warnings": exc.warnings},
        }

    return {
        "path": config_path,
        "status": "valid",
        "revision": revision,
        "raw_yaml": raw_yaml,
        "config": normalized_config,
        "diagnostics": {"errors": [], "warnings": warnings},
    }


def validate_editor_config(
    config: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[str]]:
    """Validate and normalize the editor-facing config shape."""
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []

    if config is None:
        config = empty_editor_config()

    if not isinstance(config, dict):
        raise ConfigValidationError(
            [make_error("invalid_root", "Configuration must be an object", [])]
        )

    allowed_root_keys = {"schema_version", "devices"}
    for key in config.keys():
        if key not in allowed_root_keys:
            errors.append(
                make_error(
                    "unknown_root_key",
                    f"Unsupported root key '{key}'",
                    [key],
                )
            )

    devices = config.get("devices", [])
    if not isinstance(devices, list):
        raise ConfigValidationError(
            [make_error("invalid_devices", "'devices' must be a list", ["devices"])]
        )

    normalized_devices = []
    seen_device_keys = set()
    seen_entity_ids: Dict[str, Dict[str, Any]] = {}
    seen_air_switch_buttons: set = set()

    for device_index, device in enumerate(devices):
        device_path = ["devices", device_index]
        if not isinstance(device, dict):
            errors.append(
                make_error(
                    "invalid_device",
                    "Each device must be an object",
                    device_path,
                )
            )
            continue

        allowed_device_keys = {
            "type",
            "bus_id",
            "segment_id",
            "name",
            "description",
            "outputs",
            "sensors",
            "buttons",
        }
        for key in device.keys():
            if key not in allowed_device_keys:
                errors.append(
                    make_error(
                        "unknown_device_key",
                        f"Unsupported device key '{key}'",
                        device_path + [key],
                    )
                )

        device_type = device.get("type")
        if device_type not in SUPPORTED_DEVICE_TYPES:
            errors.append(
                make_error(
                    "unsupported_device_type",
                    f"Unsupported device type '{device_type}'",
                    device_path + ["type"],
                )
            )
            continue

        bus_id = device.get("bus_id")
        if not isinstance(bus_id, int):
            errors.append(
                make_error(
                    "invalid_bus_id",
                    "bus_id must be an integer",
                    device_path + ["bus_id"],
                )
            )
            continue

        max_bus_id = 15 if device_type == "bloc9" else 255
        if not 0 <= bus_id <= max_bus_id:
            errors.append(
                make_error(
                    "invalid_bus_id_range",
                    (
                        "bus_id must be between 0 and 15"
                        if device_type == "bloc9"
                        else "bus_id must be between 0 and 255"
                    ),
                    device_path + ["bus_id"],
                )
            )
            continue

        segment_id = device.get("segment_id", 0)
        if not isinstance(segment_id, int):
            errors.append(
                make_error(
                    "invalid_segment_id",
                    "segment_id must be an integer",
                    device_path + ["segment_id"],
                )
            )
            continue

        if not 0 <= segment_id <= 7:
            errors.append(
                make_error(
                    "invalid_segment_id_range",
                    "segment_id must be between 0 and 7",
                    device_path + ["segment_id"],
                )
            )
            continue

        device_key = (device_type, bus_id, segment_id)
        if device_key in seen_device_keys:
            errors.append(
                make_error(
                    "duplicate_device",
                    f"Duplicate {device_type} bus_id {bus_id} segment_id {segment_id}",
                    device_path + ["segment_id"],
                )
            )
        seen_device_keys.add(device_key)

        name = device.get("name")
        if name is not None and not isinstance(name, str):
            errors.append(
                make_error(
                    "invalid_name",
                    "name must be a string",
                    device_path + ["name"],
                )
            )

        description = device.get("description")
        if description is not None and not isinstance(description, str):
            errors.append(
                make_error(
                    "invalid_description",
                    "description must be a string",
                    device_path + ["description"],
                )
            )

        normalized_device: Dict[str, Any] = {
            "type": device_type,
            "bus_id": bus_id,
            "segment_id": segment_id,
            "name": name.strip() if isinstance(name, str) else "",
            "description": description.strip() if isinstance(description, str) else "",
        }

        if device_type == "bloc9":
            outputs = device.get("outputs", {})
            if not isinstance(outputs, dict):
                errors.append(
                    make_error(
                        "invalid_outputs",
                        "outputs must be an object keyed by s1-s6",
                        device_path + ["outputs"],
                    )
                )
                continue

            normalized_outputs = {}
            for output_name in BLOC9_OUTPUT_KEYS:
                output = outputs.get(output_name)
                if output is None:
                    normalized_outputs[output_name] = empty_editor_output()
                    continue

                output_path = device_path + ["outputs", output_name]
                if not isinstance(output, dict):
                    errors.append(
                        make_error(
                            "invalid_output",
                            f"{output_name} must be an object",
                            output_path,
                        )
                    )
                    continue

                allowed_output_keys = {
                    "enabled",
                    "role",
                    "name",
                    "entity_id",
                    "initial_brightness",
                }
                for key in output.keys():
                    if key not in allowed_output_keys:
                        errors.append(
                            make_error(
                                "unknown_output_key",
                                f"Unsupported output key '{key}'",
                                output_path + [key],
                            )
                        )

                enabled = bool(output.get("enabled", True))
                role = output.get("role")
                output_label = output.get("name", "")
                if output_label is None:
                    output_label = ""
                if not isinstance(output_label, str):
                    errors.append(
                        make_error(
                            "invalid_output_name",
                            "name must be a string",
                            output_path + ["name"],
                        )
                    )
                    output_label = ""

                normalized_output = {
                    "enabled": enabled,
                    "role": role if enabled else None,
                    "name": output_label.strip(),
                    "entity_id": output.get("entity_id", "") if enabled else "",
                    "initial_brightness": (
                        output.get("initial_brightness") if enabled else None
                    ),
                }

                if not enabled:
                    normalized_outputs[output_name] = normalized_output
                    continue

                if role not in {"light", "switch", "pulse"}:
                    errors.append(
                        make_error(
                            "invalid_output_role",
                            "role must be 'light', 'switch', or 'pulse'",
                            output_path + ["role"],
                        )
                    )

                if not normalized_output["name"]:
                    errors.append(
                        make_error(
                            "missing_output_name",
                            "Configured outputs require a name",
                            output_path + ["name"],
                        )
                    )

                entity_id = normalized_output["entity_id"]
                if not isinstance(entity_id, str) or not entity_id.strip():
                    errors.append(
                        make_error(
                            "missing_entity_id",
                            "Configured outputs require an entity_id",
                            output_path + ["entity_id"],
                        )
                    )
                else:
                    entity_id = entity_id.strip()
                    normalized_output["entity_id"] = entity_id
                    if (
                        entity_id.startswith("light.")
                        or entity_id.startswith("switch.")
                        or entity_id.startswith("button.")
                    ):
                        errors.append(
                            make_error(
                                "entity_id_with_domain",
                                "entity_id must not include a Home Assistant domain prefix",
                                output_path + ["entity_id"],
                            )
                        )
                    elif not ENTITY_ID_RE.match(entity_id):
                        errors.append(
                            make_error(
                                "invalid_entity_id",
                                "entity_id must contain only lowercase letters, numbers, and underscores",
                                output_path + ["entity_id"],
                            )
                        )
                    elif entity_id in seen_entity_ids:
                        existing = seen_entity_ids[entity_id]
                        duplicate_is_logical_bloc9 = (
                            existing.get("kind") == "bloc9_output"
                            and existing.get("role") == role
                        )
                        if duplicate_is_logical_bloc9:
                            existing.setdefault("paths", []).append(
                                output_path + ["entity_id"]
                            )
                        else:
                            errors.append(
                                make_error(
                                    "duplicate_entity_id",
                                    f"entity_id '{entity_id}' is already used",
                                    output_path + ["entity_id"],
                                    details={
                                        "conflicts_with": existing.get("paths", [])
                                    },
                                )
                            )
                    else:
                        seen_entity_ids[entity_id] = {
                            "kind": "bloc9_output",
                            "role": role,
                            "paths": [output_path + ["entity_id"]],
                        }

                initial_brightness = normalized_output["initial_brightness"]
                if role == "light" and initial_brightness is not None:
                    if (
                        not isinstance(initial_brightness, int)
                        or not 0 <= initial_brightness <= 255
                    ):
                        errors.append(
                            make_error(
                                "invalid_initial_brightness",
                                "initial_brightness must be an integer between 0 and 255",
                                output_path + ["initial_brightness"],
                            )
                        )
                    else:
                        warnings.append(
                            f"{output_name} on bloc9 {bus_id} uses initial_brightness and will send a CAN command on startup"
                            if segment_id == 0
                            else (
                                f"{output_name} on bloc9 {bus_id}_{segment_id} uses "
                                "initial_brightness and will send a CAN command on startup"
                            )
                        )

                if role != "light" and initial_brightness is not None:
                    errors.append(
                        make_error(
                            "initial_brightness_not_allowed",
                            "initial_brightness is only supported for light outputs",
                            output_path + ["initial_brightness"],
                        )
                    )

                normalized_outputs[output_name] = normalized_output

            for output_name in outputs.keys():
                if output_name not in BLOC9_OUTPUT_KEYS:
                    errors.append(
                        make_error(
                            "invalid_output_name",
                            f"Unsupported Bloc9 output '{output_name}'",
                            device_path + ["outputs", output_name],
                        )
                    )

            normalized_device["outputs"] = normalized_outputs
        elif device_type in SENSOR_DEVICE_TYPES:
            sensors = device.get("sensors", [])
            if sensors is None:
                sensors = []
            if not isinstance(sensors, list):
                errors.append(
                    make_error(
                        "invalid_sensors",
                        "sensors must be a list",
                        device_path + ["sensors"],
                    )
                )
                continue

            normalized_sensors = []
            for sensor_index, sensor in enumerate(sensors):
                sensor_path = device_path + ["sensors", sensor_index]
                if not isinstance(sensor, dict):
                    errors.append(
                        make_error(
                            "invalid_sensor",
                            "Each sensor must be an object",
                            sensor_path,
                        )
                    )
                    continue

                allowed_sensor_keys = {
                    "name",
                    "entity_id",
                    "sensor_type",
                    "matcher",
                    "value_config",
                }
                for key in sensor.keys():
                    if key not in allowed_sensor_keys:
                        errors.append(
                            make_error(
                                "unknown_sensor_key",
                                f"Unsupported sensor key '{key}'",
                                sensor_path + [key],
                            )
                        )

                sensor_name = sensor.get("name", "")
                if not isinstance(sensor_name, str) or not sensor_name.strip():
                    errors.append(
                        make_error(
                            "missing_sensor_name",
                            f"{device_type} sensors require a name",
                            sensor_path + ["name"],
                        )
                    )
                    sensor_name = ""
                else:
                    sensor_name = sensor_name.strip()

                entity_id = sensor.get("entity_id", "")
                if not isinstance(entity_id, str) or not entity_id.strip():
                    errors.append(
                        make_error(
                            "missing_entity_id",
                            f"{device_type} sensors require an entity_id",
                            sensor_path + ["entity_id"],
                        )
                    )
                    entity_id = ""
                else:
                    entity_id = entity_id.strip()
                    if entity_id.startswith("sensor."):
                        errors.append(
                            make_error(
                                "entity_id_with_domain",
                                "entity_id must not include a Home Assistant domain prefix",
                                sensor_path + ["entity_id"],
                            )
                        )
                    elif not ENTITY_ID_RE.match(entity_id):
                        errors.append(
                            make_error(
                                "invalid_entity_id",
                                "entity_id must contain only lowercase letters, numbers, and underscores",
                                sensor_path + ["entity_id"],
                            )
                        )
                    elif entity_id in seen_entity_ids:
                        existing = seen_entity_ids[entity_id]
                        errors.append(
                            make_error(
                                "duplicate_entity_id",
                                f"entity_id '{entity_id}' is already used",
                                sensor_path + ["entity_id"],
                                details={"conflicts_with": existing.get("paths", [])},
                            )
                        )
                    else:
                        seen_entity_ids[entity_id] = {
                            "kind": "sensor",
                            "role": None,
                            "paths": [sensor_path + ["entity_id"]],
                        }

                sensor_type = sensor.get("sensor_type", "level")
                if sensor_type not in BLOC7_SENSOR_TYPES:
                    errors.append(
                        make_error(
                            "invalid_sensor_type",
                            "sensor_type must be one of: "
                            + ", ".join(sorted(BLOC7_SENSOR_TYPES)),
                            sensor_path + ["sensor_type"],
                        )
                    )
                    sensor_type = (
                        "voltage" if device_type == "source_selector" else "level"
                    )

                matcher = sensor.get("matcher")
                if not isinstance(matcher, dict):
                    errors.append(
                        make_error(
                            "invalid_matcher",
                            "matcher must be an object with pattern and mask",
                            sensor_path + ["matcher"],
                        )
                    )
                    continue

                pattern, pattern_error = _normalize_int_field(
                    matcher.get("pattern"),
                    "invalid_matcher_pattern",
                    "matcher.pattern must be an integer or hex string",
                    sensor_path + ["matcher", "pattern"],
                    min_value=0,
                )
                if pattern_error:
                    errors.append(pattern_error)

                mask, mask_error = _normalize_int_field(
                    matcher.get("mask"),
                    "invalid_matcher_mask",
                    "matcher.mask must be an integer or hex string",
                    sensor_path + ["matcher", "mask"],
                    min_value=0,
                )
                if mask_error:
                    errors.append(mask_error)

                value_config = sensor.get("value_config")
                if not isinstance(value_config, dict):
                    errors.append(
                        make_error(
                            "invalid_value_config",
                            "value_config must be an object",
                            sensor_path + ["value_config"],
                        )
                    )
                    continue

                start_byte, start_byte_error = _normalize_int_field(
                    value_config.get("start_byte"),
                    "invalid_start_byte",
                    "value_config.start_byte must be a non-negative integer",
                    sensor_path + ["value_config", "start_byte"],
                    min_value=0,
                )
                if start_byte_error:
                    errors.append(start_byte_error)

                bit_length, bit_length_error = _normalize_int_field(
                    value_config.get("bit_length"),
                    "invalid_bit_length",
                    "value_config.bit_length must be a positive integer",
                    sensor_path + ["value_config", "bit_length"],
                    min_value=1,
                )
                if bit_length_error:
                    errors.append(bit_length_error)

                endian = value_config.get("endian", "little")
                if endian not in BLOC7_ENDIAN_OPTIONS:
                    errors.append(
                        make_error(
                            "invalid_endian",
                            "value_config.endian must be 'little' or 'big'",
                            sensor_path + ["value_config", "endian"],
                        )
                    )
                    endian = "little"

                scale, scale_error = _normalize_float_field(
                    value_config.get("scale", 1.0),
                    "invalid_scale",
                    "value_config.scale must be a number",
                    sensor_path + ["value_config", "scale"],
                )
                if scale_error:
                    errors.append(scale_error)

                if (
                    start_byte is None
                    or bit_length is None
                    or pattern is None
                    or mask is None
                    or scale is None
                ):
                    continue

                normalized_sensors.append(
                    {
                        "name": sensor_name,
                        "entity_id": entity_id,
                        "sensor_type": sensor_type,
                        "matcher": {"pattern": pattern, "mask": mask},
                        "value_config": {
                            "start_byte": start_byte,
                            "bit_length": bit_length,
                            "endian": endian,
                            "scale": scale,
                        },
                    }
                )

            normalized_device["sensors"] = normalized_sensors
        elif device_type == AIR_SWITCH_DEVICE_TYPE:
            buttons = device.get("buttons", [])
            if buttons is None:
                buttons = []
            if not isinstance(buttons, list):
                errors.append(
                    make_error(
                        "invalid_buttons",
                        "buttons must be a list",
                        device_path + ["buttons"],
                    )
                )
                continue

            normalized_buttons = []
            for button_position, button in enumerate(buttons):
                button_path = device_path + ["buttons", button_position]
                if not isinstance(button, dict):
                    errors.append(
                        make_error(
                            "invalid_button",
                            "Each button must be an object",
                            button_path,
                        )
                    )
                    continue

                allowed_button_keys = {"name", "entity_id", "identity", "button_index"}
                for key in button.keys():
                    if key not in allowed_button_keys:
                        errors.append(
                            make_error(
                                "unknown_button_key",
                                f"Unsupported button key '{key}'",
                                button_path + [key],
                            )
                        )

                button_name = button.get("name", "")
                if not isinstance(button_name, str) or not button_name.strip():
                    errors.append(
                        make_error(
                            "missing_button_name",
                            "Air Switch buttons require a name",
                            button_path + ["name"],
                        )
                    )
                    button_name = ""
                else:
                    button_name = button_name.strip()

                entity_id = button.get("entity_id", "")
                if not isinstance(entity_id, str) or not entity_id.strip():
                    errors.append(
                        make_error(
                            "missing_entity_id",
                            "Air Switch buttons require an entity_id",
                            button_path + ["entity_id"],
                        )
                    )
                    entity_id = ""
                else:
                    entity_id = entity_id.strip()
                    if entity_id.startswith("event."):
                        errors.append(
                            make_error(
                                "entity_id_with_domain",
                                "entity_id must not include a Home Assistant domain prefix",
                                button_path + ["entity_id"],
                            )
                        )
                    elif not ENTITY_ID_RE.match(entity_id):
                        errors.append(
                            make_error(
                                "invalid_entity_id",
                                "entity_id must contain only lowercase letters, numbers, and underscores",
                                button_path + ["entity_id"],
                            )
                        )
                    elif entity_id in seen_entity_ids:
                        existing = seen_entity_ids[entity_id]
                        errors.append(
                            make_error(
                                "duplicate_entity_id",
                                f"entity_id '{entity_id}' is already used",
                                button_path + ["entity_id"],
                                details={"conflicts_with": existing.get("paths", [])},
                            )
                        )
                    else:
                        seen_entity_ids[entity_id] = {
                            "kind": "air_switch_button",
                            "role": None,
                            "paths": [button_path + ["entity_id"]],
                        }

                identity = button.get("identity", "")
                normalized_identity = ""
                if not isinstance(identity, str) or not AIR_SWITCH_IDENTITY_RE.match(
                    identity.strip()
                ):
                    errors.append(
                        make_error(
                            "invalid_air_switch_identity",
                            "identity must be a 6-character hex string (3 bytes), "
                            "e.g. '52AB81'",
                            button_path + ["identity"],
                        )
                    )
                else:
                    normalized_identity = identity.strip().upper()

                button_index, button_index_error = _normalize_int_field(
                    button.get("button_index"),
                    "invalid_button_index",
                    "button_index must be an integer between "
                    f"{AIR_SWITCH_BUTTON_INDEX_MIN} and {AIR_SWITCH_BUTTON_INDEX_MAX}",
                    button_path + ["button_index"],
                    min_value=AIR_SWITCH_BUTTON_INDEX_MIN,
                    max_value=AIR_SWITCH_BUTTON_INDEX_MAX,
                )
                if button_index_error:
                    errors.append(button_index_error)

                if normalized_identity and button_index is not None:
                    button_key = (normalized_identity, button_index)
                    if button_key in seen_air_switch_buttons:
                        errors.append(
                            make_error(
                                "duplicate_air_switch_button",
                                f"identity '{normalized_identity}' button_index "
                                f"{button_index} is already configured",
                                button_path + ["button_index"],
                            )
                        )
                    else:
                        seen_air_switch_buttons.add(button_key)

                normalized_buttons.append(
                    {
                        "name": button_name,
                        "entity_id": entity_id,
                        "identity": normalized_identity,
                        "button_index": button_index,
                    }
                )

            normalized_device["buttons"] = normalized_buttons
        else:  # pragma: no cover - guarded by SUPPORTED_DEVICE_TYPES validation
            continue

        normalized_devices.append(normalized_device)

    if errors:
        raise ConfigValidationError(errors, warnings)

    normalized_devices.sort(
        key=lambda item: (item["type"], item["bus_id"], item["segment_id"])
    )
    return {"schema_version": 1, "devices": normalized_devices}, warnings


def runtime_to_editor_config(runtime_config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the YAML/runtime shape to the editor-facing shape."""
    devices = runtime_config.get("devices", [])
    if devices is None:
        devices = []
    if not isinstance(devices, list):
        raise ConfigValidationError(
            [make_error("invalid_devices", "'devices' must be a list", ["devices"])]
        )

    editor_devices = []
    for device_index, device in enumerate(devices):
        if not isinstance(device, dict):
            raise ConfigValidationError(
                [
                    make_error(
                        "invalid_device",
                        "Each device must be an object",
                        ["devices", device_index],
                    )
                ]
            )

        device_type = device.get("type")
        if device_type in SENSOR_DEVICE_TYPES:
            sensors = []
            runtime_sensors = device.get("sensors")
            if runtime_sensors is None:
                runtime_sensors = []
                for sensor_type, section_name in (
                    ("voltage", "voltages"),
                    ("level", "levels"),
                ):
                    section = device.get(section_name, [])
                    if section is None:
                        continue
                    if not isinstance(section, list):
                        raise ConfigValidationError(
                            [
                                make_error(
                                    "invalid_section",
                                    f"'{section_name}' must be a list",
                                    ["devices", device_index, section_name],
                                )
                            ]
                        )
                    for sensor_index, sensor_config in enumerate(section):
                        if not isinstance(sensor_config, dict):
                            raise ConfigValidationError(
                                [
                                    make_error(
                                        "invalid_sensor",
                                        "Each sensor must be an object",
                                        [
                                            "devices",
                                            device_index,
                                            section_name,
                                            sensor_index,
                                        ],
                                    )
                                ]
                            )
                        runtime_sensors.append(
                            {
                                "sensor_type": sensor_type,
                                **sensor_config,
                            }
                        )
            if not isinstance(runtime_sensors, list):
                raise ConfigValidationError(
                    [
                        make_error(
                            "invalid_sensors",
                            "'sensors' must be a list",
                            ["devices", device_index, "sensors"],
                        )
                    ]
                )

            for sensor_index, sensor_config in enumerate(runtime_sensors):
                if not isinstance(sensor_config, dict):
                    raise ConfigValidationError(
                        [
                            make_error(
                                "invalid_sensor",
                                "Each sensor must be an object",
                                ["devices", device_index, "sensors", sensor_index],
                            )
                        ]
                    )

                matcher = sensor_config.get("matcher", {})
                value_config = sensor_config.get("value_config", {})
                sensors.append(
                    {
                        "name": sensor_config.get("name", ""),
                        "entity_id": sensor_config.get("entity_id", ""),
                        "sensor_type": sensor_config.get(
                            "sensor_type",
                            "voltage" if device_type == "source_selector" else "level",
                        ),
                        "matcher": {
                            "pattern": matcher.get("pattern"),
                            "mask": matcher.get("mask"),
                        },
                        "value_config": {
                            "start_byte": value_config.get("start_byte", 0),
                            "bit_length": value_config.get("bit_length", 8),
                            "endian": value_config.get("endian", "little"),
                            "scale": value_config.get("scale", 1.0),
                        },
                    }
                )

            editor_devices.append(
                {
                    "type": device_type,
                    "bus_id": device.get("bus_id"),
                    "segment_id": device.get("segment_id", 0),
                    "name": device.get("name", ""),
                    "description": device.get("description", ""),
                    "sensors": sensors,
                }
            )
            continue

        if device_type == AIR_SWITCH_DEVICE_TYPE:
            buttons = device.get("buttons", [])
            if buttons is None:
                buttons = []
            if not isinstance(buttons, list):
                raise ConfigValidationError(
                    [
                        make_error(
                            "invalid_buttons",
                            "'buttons' must be a list",
                            ["devices", device_index, "buttons"],
                        )
                    ]
                )

            editor_buttons = []
            for button_index, button_config in enumerate(buttons):
                if not isinstance(button_config, dict):
                    raise ConfigValidationError(
                        [
                            make_error(
                                "invalid_button",
                                "Each button must be an object",
                                ["devices", device_index, "buttons", button_index],
                            )
                        ]
                    )
                editor_buttons.append(
                    {
                        "name": button_config.get("name", ""),
                        "entity_id": button_config.get("entity_id", ""),
                        "identity": button_config.get("identity", ""),
                        "button_index": button_config.get("button_index"),
                    }
                )

            editor_devices.append(
                {
                    "type": device_type,
                    "bus_id": device.get("bus_id"),
                    "segment_id": device.get("segment_id", 0),
                    "name": device.get("name", ""),
                    "description": device.get("description", ""),
                    "buttons": editor_buttons,
                }
            )
            continue

        outputs = {
            output_name: empty_editor_output() for output_name in BLOC9_OUTPUT_KEYS
        }

        output_metadata = device.get("outputs", {})
        if output_metadata is None:
            output_metadata = {}
        if not isinstance(output_metadata, dict):
            raise ConfigValidationError(
                [
                    make_error(
                        "invalid_section",
                        "'outputs' must be an object",
                        ["devices", device_index, "outputs"],
                    )
                ]
            )

        for output_name, output_config in output_metadata.items():
            if output_name not in BLOC9_OUTPUT_KEYS:
                raise ConfigValidationError(
                    [
                        make_error(
                            "invalid_output",
                            f"Unsupported Bloc9 output '{output_name}'",
                            ["devices", device_index, "outputs", output_name],
                        )
                    ]
                )

            if not isinstance(output_config, dict):
                raise ConfigValidationError(
                    [
                        make_error(
                            "invalid_output",
                            f"{output_name} must be an object",
                            ["devices", device_index, "outputs", output_name],
                        )
                    ]
                )

            for key in output_config.keys():
                if key not in OUTPUT_METADATA_KEYS:
                    raise ConfigValidationError(
                        [
                            make_error(
                                "unknown_output_key",
                                f"Unsupported output key '{key}'",
                                ["devices", device_index, "outputs", output_name, key],
                            )
                        ]
                    )

            outputs[output_name]["name"] = output_config.get("name", "")

        for role, section_name in (
            ("light", "lights"),
            ("switch", "switches"),
            ("pulse", "pulses"),
        ):
            section = device.get(section_name, {})
            if section is None:
                section = {}
            if not isinstance(section, dict):
                raise ConfigValidationError(
                    [
                        make_error(
                            "invalid_section",
                            f"'{section_name}' must be an object",
                            ["devices", device_index, section_name],
                        )
                    ]
                )

            for output_name, output_config in section.items():
                if output_name not in BLOC9_OUTPUT_KEYS:
                    raise ConfigValidationError(
                        [
                            make_error(
                                "invalid_output",
                                f"Unsupported Bloc9 output '{output_name}'",
                                ["devices", device_index, section_name, output_name],
                            )
                        ]
                    )

                if not isinstance(output_config, dict):
                    raise ConfigValidationError(
                        [
                            make_error(
                                "invalid_output",
                                f"{output_name} must be an object",
                                ["devices", device_index, section_name, output_name],
                            )
                        ]
                    )

                outputs[output_name] = {
                    "enabled": True,
                    "role": role,
                    "name": output_config.get(
                        "name", outputs[output_name].get("name", "")
                    ),
                    "entity_id": output_config.get("entity_id", ""),
                    "initial_brightness": (
                        output_config.get("initial_brightness")
                        if role == "light"
                        else None
                    ),
                }

        editor_devices.append(
            {
                "type": device_type,
                "bus_id": device.get("bus_id"),
                "segment_id": device.get("segment_id", 0),
                "name": device.get("name", ""),
                "description": device.get("description", ""),
                "outputs": outputs,
            }
        )

    return {"schema_version": 1, "devices": editor_devices}


def editor_to_runtime_config(editor_config: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the editor-facing shape to the YAML/runtime shape."""
    runtime_devices = []
    for device in editor_config.get("devices", []):
        runtime_device: Dict[str, Any] = {
            "type": device["type"],
            "bus_id": device["bus_id"],
        }
        if device.get("segment_id", 0) != 0:
            runtime_device["segment_id"] = device["segment_id"]
        if device.get("name"):
            runtime_device["name"] = device["name"]
        if device.get("description"):
            runtime_device["description"] = device["description"]

        if device["type"] in SENSOR_DEVICE_TYPES:
            sensors = []
            for sensor in device.get("sensors", []):
                sensors.append(
                    {
                        "sensor_type": sensor["sensor_type"],
                        "name": sensor["name"],
                        "entity_id": sensor["entity_id"],
                        "matcher": {
                            "pattern": sensor["matcher"]["pattern"],
                            "mask": sensor["matcher"]["mask"],
                        },
                        "value_config": {
                            "start_byte": sensor["value_config"]["start_byte"],
                            "bit_length": sensor["value_config"]["bit_length"],
                            "endian": sensor["value_config"]["endian"],
                            "scale": sensor["value_config"]["scale"],
                        },
                    }
                )
            runtime_device["sensors"] = sensors
        elif device["type"] == AIR_SWITCH_DEVICE_TYPE:
            buttons = []
            for button in device.get("buttons", []):
                buttons.append(
                    {
                        "name": button["name"],
                        "entity_id": button["entity_id"],
                        "identity": button["identity"],
                        "button_index": button["button_index"],
                    }
                )
            runtime_device["buttons"] = buttons
        else:
            outputs = {}
            lights = {}
            switches = {}
            pulses = {}
            for output_name, output in device["outputs"].items():
                if output.get("name"):
                    outputs[output_name] = {"name": output["name"]}

                if not output["enabled"] or not output["role"]:
                    continue

                runtime_output = {
                    "name": output["name"],
                    "entity_id": output["entity_id"],
                }
                if output["role"] == "light":
                    if output.get("initial_brightness") is not None:
                        runtime_output["initial_brightness"] = output[
                            "initial_brightness"
                        ]
                    lights[output_name] = runtime_output
                elif output["role"] == "pulse":
                    pulses[output_name] = runtime_output
                else:
                    switches[output_name] = runtime_output

            if outputs:
                runtime_device["outputs"] = outputs
            if lights:
                runtime_device["lights"] = lights
            if switches:
                runtime_device["switches"] = switches
            if pulses:
                runtime_device["pulses"] = pulses

        runtime_devices.append(runtime_device)

    return {"devices": runtime_devices}


def serialize_editor_config(editor_config: Dict[str, Any]) -> str:
    """Serialize validated editor config to canonical YAML."""
    runtime_config = editor_to_runtime_config(editor_config)
    return yaml.safe_dump(runtime_config, sort_keys=False, allow_unicode=False)


def save_editor_config(
    config_path: str,
    config: Dict[str, Any],
    expected_revision: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate and atomically save editor config to disk."""
    normalized_config, warnings = validate_editor_config(copy.deepcopy(config))
    raw_yaml = serialize_editor_config(normalized_config)
    revision = compute_revision(raw_yaml)
    path = Path(config_path)

    with locked_config_path(path):
        current_raw = path.read_text(encoding="utf-8") if path.exists() else None
        current_revision = (
            compute_revision(current_raw) if current_raw is not None else None
        )
        if expected_revision is not None and expected_revision != current_revision:
            raise ConfigRevisionConflictError(
                "Configuration has changed since it was loaded"
            )

        write_atomic_text(path, raw_yaml)

    return {
        "path": config_path,
        "revision": revision,
        "raw_yaml": raw_yaml,
        "config": normalized_config,
        "diagnostics": {"errors": [], "warnings": warnings},
        "previous_raw_yaml": current_raw,
        "previous_exists": current_raw is not None,
    }


def restore_editor_config(
    config_path: str, previous_raw_yaml: Optional[str], previous_exists: bool
) -> None:
    """Restore the previous config payload after a failed apply."""
    path = Path(config_path)
    with locked_config_path(path):
        if previous_exists and previous_raw_yaml is not None:
            write_atomic_text(path, previous_raw_yaml)
        elif path.exists():
            path.unlink()


def write_atomic_text(path: Path, content: str) -> None:
    """Write file content atomically in the target directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


@contextmanager
def locked_config_path(path: Path) -> Generator[None, None, None]:
    """Serialize config writes using a sibling lock file."""
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def make_error(
    code: str, message: str, path: List[Any], details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a consistent validation error payload."""
    payload = {"code": code, "message": message, "path": path}
    if details:
        payload["details"] = details
    return payload
