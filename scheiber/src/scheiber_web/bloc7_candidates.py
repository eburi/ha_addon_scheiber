"""Heuristics for surfacing protocol-aware Scheiber sensor candidates."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scheiber.protocol import classify_message_family, decode_route, format_route_slug

FULL_MASK = 0xFFFFFFFF


def _confidence(level: str, score: int, *reasons: str) -> Dict[str, Any]:
    return {"level": level, "score": score, "reasons": list(reasons)}


def _extract_sample_value(
    data: Optional[List[int]], value_config: Dict[str, Any]
) -> Optional[float]:
    if not data:
        return None

    start_byte = int(value_config["start_byte"])
    bit_length = int(value_config.get("bit_length", 8))
    num_bytes = (bit_length + 7) // 8
    end_byte = start_byte + num_bytes
    if end_byte > len(data):
        return None

    byte_slice = bytes(int(byte) for byte in data[start_byte:end_byte])
    raw_value = int.from_bytes(
        byte_slice, value_config.get("endian", "little") or "little"
    )
    scale = float(value_config.get("scale", 1.0))
    return round(raw_value * scale, 2)


def _history_summary(
    detail: Optional[Dict[str, Any]], value_config: Dict[str, Any]
) -> List[float]:
    if not detail:
        return []

    values: List[float] = []
    for sample in reversed(detail.get("history", [])):
        value = _extract_sample_value(sample.get("data", []), value_config)
        if value is not None:
            values.append(value)
    return values[-6:]


def _current_value(
    detail: Optional[Dict[str, Any]], value_config: Dict[str, Any]
) -> Optional[float]:
    if not detail:
        return None

    return _extract_sample_value(detail.get("last_data", []), value_config)


def _sensor_suggestion(
    arbitration_id: int,
    label: str,
    start_byte: int,
    *,
    sensor_type: str = "level",
    bit_length: int = 8,
    endian: str = "little",
    scale: float = 1.0,
    notes: str,
    detail: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    slug = label.lower().replace(" ", "_")
    value_config = {
        "start_byte": start_byte,
        "bit_length": bit_length,
        "endian": endian,
        "scale": scale,
    }
    return {
        "suggestion_key": f"0x{arbitration_id:08X}:{start_byte}:{sensor_type}",
        "label": label,
        "sensor_type": sensor_type,
        "name_hint": label,
        "entity_id_hint": slug,
        "matcher": {"pattern": arbitration_id, "mask": FULL_MASK},
        "value_config": value_config,
        "current_value": _current_value(detail, value_config),
        "notes": notes,
        "history": _history_summary(detail, value_config),
    }


def _normalized_level_candidate(
    entry: Dict[str, Any],
    detail: Optional[Dict[str, Any]],
    suggestions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    arbitration_id = entry["arbitration_id_int"]
    route = decode_route(arbitration_id) or {"bus_id": 0, "segment_id": 0}
    route_slug = format_route_slug(route["bus_id"], route["segment_id"])
    return {
        "candidate_key": f"bloc7:{route_slug}:normalized_level:0x{arbitration_id:08X}",
        "device_type": "bloc7",
        "bus_id": route["bus_id"],
        "segment_id": route["segment_id"],
        "route_slug": route_slug,
        "family": "normalized_level",
        "title": f"Bloc7 #{route_slug} normalized tank frame",
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
    route = decode_route(arbitration_id) or {"bus_id": 0, "segment_id": 0}
    route_slug = format_route_slug(route["bus_id"], route["segment_id"])
    return {
        "candidate_key": f"bloc7:{route_slug}:raw_sender:0x{arbitration_id:08X}",
        "device_type": "bloc7",
        "bus_id": route["bus_id"],
        "segment_id": route["segment_id"],
        "route_slug": route_slug,
        "family": "raw_level",
        "title": f"Bloc7 #{route_slug} raw sender frame",
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
            "Matches the observed 0x020605xx raw Bloc7 family",
            "Scaling still needs manual verification against live values",
        ),
        "suggested_sensors": suggestions,
    }


def _source_selector_candidate(
    entry: Dict[str, Any],
    detail: Optional[Dict[str, Any]],
    suggestions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    arbitration_id = entry["arbitration_id_int"]
    route = decode_route(arbitration_id) or {"bus_id": 0, "segment_id": 0}
    route_slug = format_route_slug(route["bus_id"], route["segment_id"])
    return {
        "candidate_key": (
            f"source_selector:{route_slug}:ac_measurement:0x{arbitration_id:08X}"
        ),
        "device_type": "source_selector",
        "bus_id": route["bus_id"],
        "segment_id": route["segment_id"],
        "route_slug": route_slug,
        "family": "ac_measurement",
        "title": f"SourceSelector #{route_slug} AC measurement",
        "summary": (
            "This frame matches the observed SourceSelector AC measurement family. "
            "Treat it as read-only high-power AC telemetry."
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
            80,
            "Matches the observed 0x02040Bxx SourceSelector measurement family",
            "Voltage and frequency channel assignment must be confirmed manually",
        ),
        "safety_notice": (
            "Read-only telemetry only. Do not control SourceSelector relays from this bridge."
        ),
        "suggested_sensors": suggestions,
    }


def build_bloc7_candidate_snapshot(
    inspector, *, start_if_needed: bool = True
) -> Dict[str, Any]:
    """Return protocol-aware candidates derived from the shared CAN inspector."""
    snapshot = inspector.snapshot()
    if start_if_needed and snapshot["status"] != "running":
        snapshot = inspector.start()

    entries = {
        entry["arbitration_id_int"]: entry for entry in snapshot.get("entries", [])
    }
    candidates: List[Dict[str, Any]] = []

    normalized_specs = {
        0x82: [
            ("Normalized sensor byte 1", 1),
            ("Normalized sensor byte 5", 5),
        ],
        0x83: [
            ("Normalized sensor byte 1", 1),
            ("Normalized sensor byte 5", 5),
        ],
        0x8A: [
            ("Normalized sensor byte 1", 1),
            ("Normalized sensor byte 3", 3),
        ],
        0x8B: [("Normalized sensor byte 1", 1)],
    }

    for arbitration_id, entry in entries.items():
        family = classify_message_family(arbitration_id)
        if not family or family["family"] != "normalized_level":
            continue
        spec = normalized_specs.get(
            arbitration_id & 0xFF, [("Normalized sensor byte 1", 1)]
        )
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
        family = classify_message_family(arbitration_id)
        if not family or family["family"] != "raw_sender":
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
                    sensor_type="raw",
                    notes=(
                        "Single-byte raw Bloc7 sender value. Keep scale 1.0 if you "
                        "want the coarse integer reading only."
                    ),
                    detail=detail,
                ),
                _sensor_suggestion(
                    arbitration_id,
                    "Battery-style voltage bytes 4-5",
                    4,
                    sensor_type="voltage",
                    bit_length=16,
                    endian="big",
                    scale=0.1,
                    notes=(
                        "Observed as a shared two-byte big-endian voltage field. "
                        "Bytes 4-5 track the decimal battery-style reading much more "
                        "closely than byte 5 on its own."
                    ),
                    detail=detail,
                ),
            ],
        )
        candidates.append(candidate)

    for arbitration_id, entry in entries.items():
        family = classify_message_family(arbitration_id)
        if not family or family["family"] != "ac_measurement":
            continue
        detail = inspector.detail(arbitration_id)
        suggestions = []
        for offset, label in ((1, "AC input A"), (5, "AC input B")):
            suggestions.extend(
                [
                    _sensor_suggestion(
                        arbitration_id,
                        f"{label} voltage",
                        offset,
                        sensor_type="voltage",
                        notes=(
                            "Candidate SourceSelector AC voltage byte. Confirm whether "
                            "this channel is converter, generator, shore-power, or unused."
                        ),
                        detail=detail,
                    ),
                    _sensor_suggestion(
                        arbitration_id,
                        f"{label} frequency",
                        offset + 2,
                        sensor_type="frequency",
                        notes=(
                            "Candidate SourceSelector frequency byte. A value around 50 "
                            "matches 50 Hz AC sources; 0 likely means inactive."
                        ),
                        detail=detail,
                    ),
                ]
            )
        candidates.append(_source_selector_candidate(entry, detail, suggestions))

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


def build_protocol_candidate_snapshot(
    inspector, *, start_if_needed: bool = True
) -> Dict[str, Any]:
    """Return all protocol-aware candidates for web UI and MCP callers."""
    return build_bloc7_candidate_snapshot(inspector, start_if_needed=start_if_needed)
