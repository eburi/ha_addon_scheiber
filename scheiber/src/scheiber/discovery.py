"""Bloc9 discovery helpers for raw CAN traffic classification."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import can

from .output import Output
from .protocol import (
    BLOC9_STATUS_PREFIX,
    build_address_byte,
    decode_route,
    format_route_slug,
)

BLOC9_HEARTBEAT_PREFIX = BLOC9_STATUS_PREFIX
BLOC9_STATE_GROUPS: Dict[int, Tuple[str, int, str, int]] = {
    0x02160600: ("s1", 0, "s2", 1),
    0x02180600: ("s3", 2, "s4", 3),
    0x021A0600: ("s5", 4, "s6", 5),
}


def format_bloc9_route_slug(bus_id: int, segment_id: int = 0) -> str:
    """Format a bus/segment identity for topics, state keys, and UI labels."""
    return format_route_slug(bus_id, segment_id)


def build_bloc9_address_byte(bus_id: int, segment_id: int = 0) -> int:
    """Build the Bloc9 arbitration-ID low byte from bus ID and segment ID."""
    return build_address_byte(bus_id, segment_id)


def decode_bloc9_address(arbitration_id: int) -> Optional[Dict[str, int]]:
    """Decode the Bloc9 arbitration-ID low byte into bus ID and segment ID."""
    return decode_route(arbitration_id)


def decode_bloc9_bus_id(arbitration_id: int) -> Optional[int]:
    """Decode a Bloc9 bus ID from the arbitration ID low byte."""
    address = decode_bloc9_address(arbitration_id)
    if address is None:
        return None
    return address["bus_id"]


def classify_bloc9_message(msg: can.Message) -> Optional[Dict[str, Any]]:
    """
    Classify a raw CAN message as a potential Bloc9 observation.

    Returns None for unrelated messages.
    """
    address = decode_bloc9_address(msg.arbitration_id)
    if address is None:
        return None
    bus_id = address["bus_id"]
    segment_id = address["segment_id"]
    candidate_key = f"{bus_id}:{segment_id}"

    prefix = msg.arbitration_id & 0xFFFFFF00
    if prefix in BLOC9_STATE_GROUPS:
        lower_name, lower_switch_nr, upper_name, upper_switch_nr = BLOC9_STATE_GROUPS[
            prefix
        ]
        lower_state = decode_output_sample(msg, lower_switch_nr)
        upper_state = decode_output_sample(msg, upper_switch_nr)
        return {
            "kind": "state_update",
            "bus_id": bus_id,
            "segment_id": segment_id,
            "route_slug": format_bloc9_route_slug(bus_id, segment_id),
            "candidate_key": candidate_key,
            "is_segmented": segment_id != 0,
            "group": f"{lower_name}_{upper_name}",
            "arbitration_id": f"0x{msg.arbitration_id:08X}",
            "outputs": {
                lower_name: lower_state,
                upper_name: upper_state,
            },
        }

    if prefix == BLOC9_HEARTBEAT_PREFIX:
        return {
            "kind": "heartbeat",
            "bus_id": bus_id,
            "segment_id": segment_id,
            "route_slug": format_bloc9_route_slug(bus_id, segment_id),
            "candidate_key": candidate_key,
            "is_segmented": segment_id != 0,
            "arbitration_id": f"0x{msg.arbitration_id:08X}",
        }

    return None


def decode_output_sample(msg: can.Message, switch_nr: int) -> Dict[str, Any]:
    """Decode a single output sample from a Bloc9 state update message."""
    state, brightness = Output.get_state_from_can_message(msg, switch_nr)
    effective_brightness = 255 if state and brightness == 0 else brightness
    return {
        "state": state,
        "raw_brightness": brightness,
        "effective_brightness": effective_brightness,
    }
