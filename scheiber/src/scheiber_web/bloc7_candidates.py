"""Heuristics for surfacing likely Bloc7 sensor candidates from raw CAN traffic."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

FULL_MASK = 0xFFFFFFFF


def _confidence(level: str, score: int, *reasons: str) -> Dict[str, Any]:
    return {"level": level, "score": score, "reasons": list(reasons)}


def _history_summary(detail: Optional[Dict[str, Any]], start_byte: int) -> List[int]:
    if not detail:
        return []

    values: List[int] = []
    for sample in reversed(detail.get("history", [])):
        data = sample.get("data", [])
        if start_byte < len(data):
            values.append(int(data[start_byte]))
    return values[-6:]


def _sensor_suggestion(
    arbitration_id: int,
    label: str,
    start_byte: int,
    *,
    sensor_type: str = "level",
    scale: float = 1.0,
    notes: str,
    detail: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    slug = label.lower().replace(" ", "_")
    return {
        "suggestion_key": f"0x{arbitration_id:08X}:{start_byte}:{sensor_type}",
        "label": label,
        "sensor_type": sensor_type,
        "name_hint": label,
        "entity_id_hint": slug,
        "matcher": {"pattern": arbitration_id, "mask": FULL_MASK},
        "value_config": {
            "start_byte": start_byte,
            "bit_length": 8,
            "endian": "little",
            "scale": scale,
        },
        "notes": notes,
        "history": _history_summary(detail, start_byte),
    }


def _normalized_level_candidate(
    entry: Dict[str, Any],
    detail: Optional[Dict[str, Any]],
    suggestions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    arbitration_id = entry["arbitration_id_int"]
    return {
        "candidate_key": f"bloc7-normalized-0x{arbitration_id:08X}",
        "family": "normalized_level",
        "title": f"Normalized Bloc7 tank frame 0x{arbitration_id:08X}",
        "summary": (
            "This frame matches the live-normalized Bloc7 tank family that tracked "
            "SignalK percentage values during reverse engineering."
        ),
        "arbitration_id": entry["arbitration_id"],
        "arbitration_id_int": arbitration_id,
        "freq_hz": entry.get("freq_hz", 0),
        "last_data": entry.get("last_data", []),
        "recent_history": [
            sample.get("data", []) for sample in (detail or {}).get("history", [])[:6]
        ],
        "confidence": _confidence(
            "high",
            95,
            "Matches the observed 0x020405xx / 0x02060583 normalized tank-value family",
            "Suggested bytes are the ones that tracked live percentage changes",
        ),
        "suggested_sensors": suggestions,
    }


def _raw_level_candidate(
    entry: Dict[str, Any],
    detail: Optional[Dict[str, Any]],
    suggestions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    arbitration_id = entry["arbitration_id_int"]
    return {
        "candidate_key": f"bloc7-raw-0x{arbitration_id:08X}",
        "family": "raw_level",
        "title": f"Raw Bloc7 sender frame 0x{arbitration_id:08X}",
        "summary": (
            "This frame matches the secondary Bloc7 raw/resistance-looking family. "
            "It is likely useful for manual correlation, but its scaling is not yet proven."
        ),
        "arbitration_id": entry["arbitration_id"],
        "arbitration_id_int": arbitration_id,
        "freq_hz": entry.get("freq_hz", 0),
        "last_data": entry.get("last_data", []),
        "recent_history": [
            sample.get("data", []) for sample in (detail or {}).get("history", [])[:6]
        ],
        "confidence": _confidence(
            "medium",
            65,
            "Matches the observed 0x02040Bxx raw Bloc7 family",
            "Scaling still needs manual verification against live values",
        ),
        "suggested_sensors": suggestions,
    }


def build_bloc7_candidate_snapshot(
    inspector, *, start_if_needed: bool = True
) -> Dict[str, Any]:
    """Return Bloc7-oriented candidates derived from the shared CAN inspector."""
    snapshot = inspector.snapshot()
    if start_if_needed and snapshot["status"] != "running":
        snapshot = inspector.start()

    entries = {
        entry["arbitration_id_int"]: entry for entry in snapshot.get("entries", [])
    }
    candidates: List[Dict[str, Any]] = []

    normalized_specs = {
        0x02040582: [
            ("Normalized sensor byte 1", 1),
            ("Normalized sensor byte 5", 5),
        ],
        0x02040583: [
            ("Normalized sensor byte 1", 1),
            ("Normalized sensor byte 5", 5),
        ],
        0x0204058A: [
            ("Normalized sensor byte 1", 1),
            ("Normalized sensor byte 3", 3),
        ],
        0x0204058B: [("Normalized sensor byte 1", 1)],
        0x02060583: [("Normalized sensor byte 1", 1)],
    }

    for arbitration_id, spec in normalized_specs.items():
        entry = entries.get(arbitration_id)
        if not entry:
            continue
        detail = inspector.detail(arbitration_id)
        suggestions = [
            _sensor_suggestion(
                arbitration_id,
                label,
                start_byte,
                notes=(
                    "Observed as a normalized 0-100 style Bloc7 value. "
                    "Use this as a manual draft and confirm the tank or level assignment."
                ),
                detail=detail,
            )
            for label, start_byte in spec
        ]
        candidates.append(_normalized_level_candidate(entry, detail, suggestions))

    for arbitration_id, entry in entries.items():
        if (arbitration_id & 0xFFFFFF00) != 0x02040B00:
            continue
        detail = inspector.detail(arbitration_id)
        candidate = _raw_level_candidate(
            entry,
            detail,
            [
                _sensor_suggestion(
                    arbitration_id,
                    "Raw sender byte 1",
                    1,
                    notes=(
                        "Candidate raw Bloc7 sender value. Keep scale 1.0 until the "
                        "real resistance or voltage conversion is known."
                    ),
                    detail=detail,
                ),
                _sensor_suggestion(
                    arbitration_id,
                    "Raw sender byte 5",
                    5,
                    notes=(
                        "Candidate raw Bloc7 sender value. Keep scale 1.0 until the "
                        "real resistance or voltage conversion is known."
                    ),
                    detail=detail,
                ),
            ],
        )
        candidates.append(candidate)

    candidates.sort(
        key=lambda item: (-item["confidence"]["score"], item["arbitration_id_int"])
    )
    return {
        "status": snapshot["status"],
        "started_at": snapshot.get("started_at"),
        "last_message_at": snapshot.get("last_message_at"),
        "total_messages": snapshot.get("total_messages", 0),
        "unique_ids": snapshot.get("unique_ids", 0),
        "candidates": candidates,
    }
