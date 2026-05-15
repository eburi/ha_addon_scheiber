"""
Bloc9 discovery helpers for raw CAN traffic classification.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import can

from .output import Output

BLOC9_HEARTBEAT_PREFIX = 0x00000600
BLOC9_STATE_GROUPS: Dict[int, Tuple[str, int, str, int]] = {
    0x02160600: ("s1", 0, "s2", 1),
    0x02180600: ("s3", 2, "s4", 3),
    0x021A0600: ("s5", 4, "s6", 5),
}


def decode_bloc9_bus_id(arbitration_id: int) -> Optional[int]:
    """Decode a Bloc9 bus ID from the arbitration ID low byte."""
    low_byte = arbitration_id & 0xFF
    if (low_byte & 0x80) != 0x80:
        return None
    if (low_byte & 0x07) != 0:
        return None
    return (low_byte & 0x7F) >> 3


def classify_bloc9_message(msg: can.Message) -> Optional[Dict[str, Any]]:
    """
    Classify a raw CAN message as a potential Bloc9 observation.

    Returns None for unrelated messages.
    """
    bus_id = decode_bloc9_bus_id(msg.arbitration_id)
    if bus_id is None:
        return None

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
