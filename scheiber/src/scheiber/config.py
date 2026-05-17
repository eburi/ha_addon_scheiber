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
BLOC9_OUTPUT_KEYS = tuple(f"s{i}" for i in range(1, 7))
SUPPORTED_DEVICE_TYPES = {"bloc9"}
OUTPUT_METADATA_KEYS = {"name"}


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
    seen_entity_ids = {}

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

        if not 0 <= bus_id <= 15:
            errors.append(
                make_error(
                    "invalid_bus_id_range",
                    "bus_id must be between 0 and 15",
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

            if role not in {"light", "switch"}:
                errors.append(
                    make_error(
                        "invalid_output_role",
                        "role must be 'light' or 'switch'",
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
                if entity_id.startswith("light.") or entity_id.startswith("switch."):
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
                    errors.append(
                        make_error(
                            "duplicate_entity_id",
                            f"entity_id '{entity_id}' is already used",
                            output_path + ["entity_id"],
                            details={"conflicts_with": seen_entity_ids[entity_id]},
                        )
                    )
                else:
                    seen_entity_ids[entity_id] = output_path + ["entity_id"]

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

        normalized_devices.append(
            {
                "type": device_type,
                "bus_id": bus_id,
                "segment_id": segment_id,
                "name": name.strip() if isinstance(name, str) else "",
                "description": (
                    description.strip() if isinstance(description, str) else ""
                ),
                "outputs": normalized_outputs,
            }
        )

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

        for role, section_name in (("light", "lights"), ("switch", "switches")):
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
                "type": device.get("type"),
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

        outputs = {}
        lights = {}
        switches = {}
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
                    runtime_output["initial_brightness"] = output["initial_brightness"]
                lights[output_name] = runtime_output
            else:
                switches[output_name] = runtime_output

        if outputs:
            runtime_device["outputs"] = outputs
        if lights:
            runtime_device["lights"] = lights
        if switches:
            runtime_device["switches"] = switches

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
