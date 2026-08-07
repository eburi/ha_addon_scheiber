"""Helpers for provisional Scheiber button-source discovery."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import can

KNOWN_BUTTON_SOURCE_IDS = {
    0x04001A80: "wireless_light_air_switch_interface",
    0x04001808: "button_panel_or_key_interface",
}

# Confirmed wireless Light Air Switch family (see
# plan/button-interaction-hypothesis.md). Every logical press/release is
# broadcast redundantly on 0x04001A80/0x04001A82/0x04001A83 with identical
# payloads; the low byte is not a Bloc9 bus/segment target.
AIR_SWITCH_PREFIX = 0x04001A00
AIR_SWITCH_MASK = 0xFFFFFF00
AIR_SWITCH_LEADER_BYTE = 0x01
AIR_SWITCH_BUTTON_INDEX_MASK = 0x7F
AIR_SWITCH_PRESSED_BIT = 0x80


def classify_air_switch_message(msg: can.Message) -> Optional[Dict[str, Any]]:
    """Classify a confirmed Scheiber wireless Air Switch button frame.

    Unlike :func:`classify_button_source_message` (which is intentionally
    broad/provisional for investigation), this only matches the empirically
    confirmed wireless schema: arbitration IDs under the 0x04001A00 prefix
    carrying a 5-byte payload `01 <3-byte identity> <status>`, where the
    identity bytes are non-zero (ruling out the deferred wired-family shape,
    which always carries a constant zero identity). Returns None for
    anything that does not match this exact confirmed shape.
    """
    data = bytes(msg.data)
    if len(data) != 5:
        return None
    if (msg.arbitration_id & AIR_SWITCH_MASK) != AIR_SWITCH_PREFIX:
        return None
    if data[0] != AIR_SWITCH_LEADER_BYTE:
        return None

    identity = data[1:4]
    if identity == b"\x00\x00\x00":
        # Matches the deferred wired-family zero-identity shape.
        return None

    status_byte = data[4]
    return {
        "kind": "air_switch_button",
        "arbitration_id": f"0x{msg.arbitration_id:08X}",
        "identity_hex": identity.hex().upper(),
        "button_index": status_byte & AIR_SWITCH_BUTTON_INDEX_MASK,
        "pressed": bool(status_byte & AIR_SWITCH_PRESSED_BIT),
        "status_hex": f"0x{status_byte:02X}",
        "data_hex": data.hex().upper(),
    }


def classify_button_source_message(msg: can.Message) -> Optional[Dict[str, Any]]:
    """Classify raw CAN frames that look like button-source status frames.

    This is intentionally provisional.  Local captures show battery-less
    wireless button traffic on 0x04001A80 and wired/panel button traffic on
    0x04001808.  Both use compact payloads where the final byte changes with
    press/release state.  The first payload bytes are treated as an observed
    identity, not as a decoded stable address contract.
    """
    data = bytes(msg.data)
    if not data:
        return None

    arbitration_id = int(msg.arbitration_id)
    known_family = arbitration_id in KNOWN_BUTTON_SOURCE_IDS
    likely_family = (arbitration_id & 0xFF000000) == 0x04000000 and len(data) == 5
    if not (known_family or likely_family):
        return None

    status_byte = data[-1]
    identity_bytes = data[:-1]
    active_bits = _active_bits(status_byte, width=8)
    lower_status = status_byte & 0x7F

    confidence = "high" if known_family and len(data) == 5 else "medium"
    if known_family and len(data) != 5:
        confidence = "low"

    return {
        "kind": "button_source_status",
        "arbitration_id": f"0x{arbitration_id:08X}",
        "source_family": KNOWN_BUTTON_SOURCE_IDS.get(
            arbitration_id, "unknown_0x04_button_candidate"
        ),
        "candidate_key": f"0x{arbitration_id:08X}:{identity_bytes.hex().upper()}",
        "identity_hex": identity_bytes.hex().upper(),
        "status_byte": status_byte,
        "status_hex": f"0x{status_byte:02X}",
        "active_bits": active_bits,
        "lower_status": lower_status,
        "lower_status_hex": f"0x{lower_status:02X}",
        "lower_active_bits": _active_bits(lower_status, width=7),
        "high_bit_set": bool(status_byte & 0x80),
        "data_hex": data.hex().upper(),
        "dlc": len(data),
        "confidence": confidence,
    }


def diff_status_bits(previous_status: int, current_status: int) -> Dict[str, List[int]]:
    """Return rising/falling bit transitions between two status bytes."""
    changed = previous_status ^ current_status
    return {
        "rising_bits": [
            bit for bit in range(8) if changed & current_status & (1 << bit)
        ],
        "falling_bits": [
            bit for bit in range(8) if changed & previous_status & (1 << bit)
        ],
    }


def _active_bits(value: int, *, width: int) -> List[int]:
    return [bit for bit in range(width) if value & (1 << bit)]
