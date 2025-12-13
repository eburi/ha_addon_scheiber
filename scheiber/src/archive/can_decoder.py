#!/usr/bin/env python3
"""
CAN message decoder for Scheiber devices.

Provides device-agnostic utilities for parsing CAN messages based on YAML configuration.
This module is used by both canlistener.py (debug tool) and mqtt_bridge.py (production).
"""

import os

import yaml


def _load_device_types():
    """Load device type definitions from device_types.yaml."""
    config_path = os.path.join(os.path.dirname(__file__), "device_types.yaml")

    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)

    device_types = {}

    for device_key, device_config in raw_config.items():
        # Convert bus_id_extractor formula to lambda
        extractor_config = device_config.get("bus_id_extractor", {})
        if extractor_config.get("type") == "formula":
            formula = extractor_config["formula"]
            # Create lambda from formula string (safe for our controlled input)
            bus_id_extractor = eval(f"lambda arb_id: {formula}")
        else:
            # Default extractor
            bus_id_extractor = lambda arb_id: (arb_id & 0xFF)

        device_types[device_key] = {
            "name": device_config["name"],
            "bus_id_extractor": bus_id_extractor,
            "matchers": device_config.get("matchers", []),
        }

    return device_types


# Load device types at module import
DEVICE_TYPES = _load_device_types()


def find_device_and_matcher(arb_id):
    """Find device type and matching matcher for an arbitration ID.

    Returns (device_type_key, device_config, matcher, bus_id) or (None, None, None, None).
    """
    for device_key, device_config in DEVICE_TYPES.items():
        for matcher in device_config["matchers"]:
            if (arb_id & matcher["mask"]) == (matcher["address"] & matcher["mask"]):
                bus_id = device_config["bus_id_extractor"](arb_id)
                return device_key, device_config, matcher, bus_id
    return None, None, None, None


def _parse_template(template):
    """Parse a template string into extraction parameters.

    Supports:
      - Bit extraction: '(byte_index,bit_index)' -> ('bit', byte_idx, bit_idx)
      - Byte extraction: '[byte_index]' -> ('byte', byte_idx, None)

    Returns ('bit'|'byte', byte_index, bit_index|None) or None if parsing fails.
    """
    try:
        template = template.strip()

        # Bit extraction: (byte_idx, bit_idx)
        if template.startswith("(") and template.endswith(")"):
            parts = template[1:-1].split(",")
            if len(parts) == 2:
                byte_idx = int(parts[0].strip())
                bit_idx = int(parts[1].strip())
                return ("bit", byte_idx, bit_idx)

        # Byte extraction: [byte_idx]
        elif template.startswith("[") and template.endswith("]"):
            byte_idx = int(template[1:-1].strip())
            return ("byte", byte_idx, None)

    except (ValueError, AttributeError):
        pass
    return None


def extract_property_value(raw, template):
    """Extract a property value from raw CAN data using a template.

    Args:
        raw: bytes object containing CAN message data
        template: string like '(3,0)' for bit or '[4]' for byte extraction

    Returns:
        For bit extraction: 1 if bit is set, 0 if bit is clear
        For byte extraction: integer value 0-255
        None if extraction fails
    """
    parsed = _parse_template(template)
    if parsed is None:
        return None

    extract_type, byte_idx, bit_idx = parsed
    if byte_idx >= len(raw):
        return None

    if extract_type == "bit":
        if bit_idx is None:
            return None
        return 1 if (raw[byte_idx] & (1 << bit_idx)) else 0
    elif extract_type == "byte":
        return raw[byte_idx]
