"""Shared Scheiber CAN protocol helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional

ADDRESS_FLAG = 0x80
BUS_ID_MASK = 0x78
SEGMENT_ID_MASK = 0x07

BLOC7_STATUS_PREFIX = 0x00000500
BLOC9_STATUS_PREFIX = 0x00000600
SOURCE_SELECTOR_STATUS_PREFIX = 0x00000B00
BLOC7_NORMALIZED_PREFIX = 0x02040500
BLOC7_RAW_PREFIX = 0x02060500
SOURCE_SELECTOR_AC_PREFIX = 0x02040B00
SOURCE_SELECTOR_DC_PREFIX = 0x02060B00
SOURCE_SELECTOR_ENGINE_STATE_PREFIX = 0x02140B00
SOURCE_SELECTOR_OUTPUT_STATE_PREFIX = 0x02160B00
SOURCE_SELECTOR_PHASE_PREFIX = 0x02440B00
SOURCE_SELECTOR_COMMAND_PREFIX = 0x02460B00

# Generator remote-control command bytes sent on SOURCE_SELECTOR_COMMAND_PREFIX.
# The node pulses its start relay (output 1) for 30 s on START and its stop
# relay (output 2) for 60 s on STOP. See plan/generator-control.md.
GENERATOR_COMMAND_START = 0x01
GENERATOR_COMMAND_STOP = 0x02


def format_route_slug(bus_id: int, segment_id: int = 0) -> str:
    """Format a bus/segment identity for topics, state keys, and UI labels."""
    return f"{bus_id}" if segment_id == 0 else f"{bus_id}_{segment_id}"


def build_address_byte(bus_id: int, segment_id: int = 0) -> int:
    """Build the shared Scheiber arbitration-ID low byte."""
    if not 0 <= bus_id <= 15:
        raise ValueError("bus_id must be between 0 and 15")
    if not 0 <= segment_id <= 7:
        raise ValueError("segment_id must be between 0 and 7")
    return ADDRESS_FLAG | (bus_id << 3) | segment_id


def decode_route(arbitration_id: int) -> Optional[Dict[str, int]]:
    """Decode the shared Scheiber low-byte route from an arbitration ID."""
    low_byte = arbitration_id & 0xFF
    if (low_byte & ADDRESS_FLAG) != ADDRESS_FLAG:
        return None

    bus_id = (low_byte & BUS_ID_MASK) >> 3
    segment_id = low_byte & SEGMENT_ID_MASK
    return {
        "bus_id": bus_id,
        "segment_id": segment_id,
        "low_byte": low_byte,
    }


def _base_classification(arbitration_id: int) -> Optional[Dict[str, Any]]:
    route = decode_route(arbitration_id)
    if route is None:
        return None
    return {
        "bus_id": route["bus_id"],
        "segment_id": route["segment_id"],
        "route_slug": format_route_slug(route["bus_id"], route["segment_id"]),
        "candidate_key": f"{route['bus_id']}:{route['segment_id']}",
        "is_segmented": route["segment_id"] != 0,
        "low_byte": route["low_byte"],
        "arbitration_id": f"0x{arbitration_id:08X}",
    }


def classify_message_family(arbitration_id: int) -> Optional[Dict[str, Any]]:
    """Classify known Scheiber message families without decoding payloads."""
    prefix = arbitration_id & 0xFFFFFF00
    base = _base_classification(arbitration_id)
    if base is None:
        return None

    family_map = {
        BLOC7_STATUS_PREFIX: ("bloc7", "status"),
        BLOC9_STATUS_PREFIX: ("bloc9", "status"),
        SOURCE_SELECTOR_STATUS_PREFIX: ("source_selector", "status"),
        BLOC7_NORMALIZED_PREFIX: ("bloc7", "normalized_level"),
        BLOC7_RAW_PREFIX: ("bloc7", "raw_sender"),
        SOURCE_SELECTOR_AC_PREFIX: ("source_selector", "ac_measurement"),
        SOURCE_SELECTOR_DC_PREFIX: ("source_selector", "dc_measurement"),
        SOURCE_SELECTOR_ENGINE_STATE_PREFIX: ("source_selector", "engine_state"),
        SOURCE_SELECTOR_OUTPUT_STATE_PREFIX: ("source_selector", "output_state"),
        SOURCE_SELECTOR_PHASE_PREFIX: ("source_selector", "phase"),
        SOURCE_SELECTOR_COMMAND_PREFIX: ("source_selector", "command"),
    }
    device_type, family = family_map.get(prefix, (None, None))
    if device_type is None:
        return None

    return {
        **base,
        "device_type": device_type,
        "family": family,
        "prefix": f"0x{prefix:08X}",
        "is_provisional": family in {"status", "raw_sender"},
    }
