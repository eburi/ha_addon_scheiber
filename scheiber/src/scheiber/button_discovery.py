"""Helpers for provisional Scheiber button-source discovery."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import can


KNOWN_BUTTON_SOURCE_IDS = {
    0x04001A80: "wireless_light_air_switch_interface",
    0x04001808: "button_panel_or_key_interface",
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
        "rising_bits": [bit for bit in range(8) if changed & current_status & (1 << bit)],
        "falling_bits": [bit for bit in range(8) if changed & previous_status & (1 << bit)],
    }


def _active_bits(value: int, *, width: int) -> List[int]:
    return [bit for bit in range(width) if value & (1 << bit)]
