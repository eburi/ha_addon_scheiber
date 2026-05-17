"""CAN Bus Inspector service for reverse engineering and protocol discovery."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

import can

from scheiber.discovery import (
    classify_bloc9_message,
    decode_bloc9_address,
    format_bloc9_route_slug,
)

MAX_HISTORY = 30
BLOC9_COMMAND_PREFIX = 0x02360600


def _compute_bit_diff(
    prev: Optional[bytes], curr: Optional[bytes]
) -> List[Dict[str, Any]]:
    """Return per-byte bit-level diff between prev and curr data."""
    if prev is None or curr is None:
        return []

    result = []
    max_len = max(len(prev), len(curr))
    for i in range(max_len):
        prev_byte = prev[i] if i < len(prev) else 0
        curr_byte = curr[i] if i < len(curr) else 0
        changed = prev_byte != curr_byte
        changed_positions = []
        for bit in range(8):
            if ((prev_byte >> bit) & 1) != ((curr_byte >> bit) & 1):
                changed_positions.append(bit)
        result.append(
            {
                "byte_index": i,
                "prev_byte": prev_byte,
                "curr_byte": curr_byte,
                "changed": changed,
                "changed_bit_positions": changed_positions,
                "prev_bits": f"{prev_byte:08b}",
                "curr_bits": f"{curr_byte:08b}",
            }
        )
    return result


def _brightness_percent(brightness: int) -> int:
    """Convert a 0-255 brightness value into a UI-friendly percentage."""
    return round((brightness / 255) * 100)


def _format_output_state(name: str, state: Dict[str, Any]) -> str:
    """Format a decoded Bloc9 output state for the inspector UI."""
    output_name = name.upper()
    if not state["state"]:
        return f"{output_name}: OFF"

    percent = _brightness_percent(state["effective_brightness"])
    if percent >= 100:
        return f"{output_name}: ON"
    return f"{output_name}: ON, {percent}%"


def _format_command_state(switch_nr: int, mode: int, brightness: int) -> str:
    """Format a Bloc9 command payload for the inspector UI."""
    output_name = f"S{switch_nr + 1}" if 0 <= switch_nr <= 5 else f"Switch {switch_nr}"
    if mode == 0x00:
        return f"{output_name}: OFF"
    if mode == 0x01:
        return f"{output_name}: ON"
    if mode == 0x11:
        return f"{output_name}: ON, {_brightness_percent(brightness)}%"
    return f"{output_name}: mode 0x{mode:02X}"


def _describe_known_message(arbitration_id: int, data: bytes) -> Dict[str, Any]:
    """Return decoded human-readable metadata for known CAN messages."""
    msg = can.Message(
        arbitration_id=arbitration_id,
        data=data,
        is_extended_id=arbitration_id > 0x7FF,
    )

    bloc9 = classify_bloc9_message(msg)
    if bloc9 is not None:
        route_slug = bloc9["route_slug"]
        if bloc9["kind"] == "heartbeat":
            return {
                "is_known": True,
                "known_kind": "bloc9_heartbeat",
                "known_messages": [f"Bloc9 #{route_slug} heartbeat"],
            }

        output_states = ", ".join(
            _format_output_state(name, state)
            for name, state in bloc9["outputs"].items()
        )
        return {
            "is_known": True,
            "known_kind": "bloc9_state_update",
            "known_messages": [f"Bloc9 #{route_slug} state update", output_states],
        }

    if (arbitration_id & 0xFFFFFF00) == BLOC9_COMMAND_PREFIX:
        address = decode_bloc9_address(arbitration_id)
        if address is not None:
            route_slug = format_bloc9_route_slug(
                address["bus_id"], address["segment_id"]
            )
            switch_nr = data[0] if len(data) > 0 else -1
            mode = data[1] if len(data) > 1 else 0
            brightness = data[3] if len(data) > 3 else 0
            return {
                "is_known": True,
                "known_kind": "bloc9_command",
                "known_messages": [
                    f"Bloc9 #{route_slug} command",
                    _format_command_state(switch_nr, mode, brightness),
                ],
            }

    return {"is_known": False, "known_kind": None, "known_messages": []}


class CanInspector:
    """Capture and analyse all raw CAN messages for reverse engineering."""

    def __init__(self, runtime_controller) -> None:
        self.runtime_controller = runtime_controller
        self._lock = threading.RLock()
        self._active = False
        self._started_at: Optional[float] = None
        self._last_message_at: Optional[float] = None
        self._total_messages = 0
        # keyed by int arbitration_id
        self._table: Dict[int, Dict[str, Any]] = {}

    @property
    def _can_interface(self) -> str:
        return self.runtime_controller.settings.can_interface

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> Dict[str, Any]:
        """Start (or restart) capturing. Resets all state."""
        with self._lock:
            if self._active:
                self.runtime_controller.unsubscribe_from_messages(self._handle_message)

            self._table = {}
            self._total_messages = 0
            self._started_at = time.time()
            self._last_message_at = None
            self._active = True
            self.runtime_controller.subscribe_to_messages(self._handle_message)
            return self.snapshot()

    def stop(self) -> Dict[str, Any]:
        """Stop capturing and return the final snapshot."""
        with self._lock:
            if self._active:
                self.runtime_controller.unsubscribe_from_messages(self._handle_message)
            self._active = False
            return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        """Return a lightweight JSON-serialisable snapshot (no history)."""
        with self._lock:
            entries = []
            now = time.time()
            for arb_id, entry in sorted(self._table.items()):
                elapsed = now - entry["first_seen"]
                freq = entry["count"] / elapsed if elapsed > 0 else 0.0
                last_data = list(entry["last_data"])
                prev_data = list(entry["prev_data"]) if entry["prev_data"] else None
                known_info = _describe_known_message(arb_id, entry["last_data"])
                entries.append(
                    {
                        "arbitration_id": f"0x{arb_id:08X}",
                        "arbitration_id_int": arb_id,
                        "count": entry["count"],
                        "first_seen": entry["first_seen"],
                        "last_seen": entry["last_seen"],
                        "freq_hz": round(freq, 2),
                        "dlc": entry["dlc"],
                        "last_data": last_data,
                        "prev_data": prev_data,
                        "data_changed": entry["prev_data"] is not None
                        and entry["prev_data"] != entry["last_data"],
                        "is_known": known_info["is_known"],
                        "known_kind": known_info["known_kind"],
                        "known_messages": known_info["known_messages"],
                    }
                )
            return {
                "status": "running" if self._active else "stopped",
                "can_interface": self._can_interface,
                "started_at": self._started_at,
                "last_message_at": self._last_message_at,
                "total_messages": self._total_messages,
                "unique_ids": len(self._table),
                "entries": entries,
            }

    def detail(self, arb_id: int) -> Optional[Dict[str, Any]]:
        """Return full history + bit diff for a single arbitration ID."""
        with self._lock:
            entry = self._table.get(arb_id)
            if entry is None:
                return None

            now = time.time()
            elapsed = now - entry["first_seen"]
            freq = entry["count"] / elapsed if elapsed > 0 else 0.0

            last_data = entry["last_data"]
            prev_data = entry["prev_data"]
            known_info = _describe_known_message(arb_id, last_data)

            history_out = []
            raw_history = list(entry["history"])  # oldest → newest
            for i, h in enumerate(raw_history):
                if i == 0:
                    h_prev = None
                else:
                    h_prev = raw_history[i - 1]["data"]
                bd = _compute_bit_diff(h_prev, h["data"])
                history_out.append(
                    {
                        "timestamp": h["timestamp"],
                        "data": list(h["data"]),
                        "bit_diff": bd,
                    }
                )
            # newest first for display
            history_out.reverse()

            return {
                "arbitration_id": f"0x{arb_id:08X}",
                "arbitration_id_int": arb_id,
                "count": entry["count"],
                "first_seen": entry["first_seen"],
                "last_seen": entry["last_seen"],
                "freq_hz": round(freq, 2),
                "dlc": entry["dlc"],
                "last_data": list(last_data),
                "prev_data": list(prev_data) if prev_data else None,
                "bit_diff": _compute_bit_diff(prev_data, last_data),
                "history": history_out,
                "is_known": known_info["is_known"],
                "known_kind": known_info["known_kind"],
                "known_messages": known_info["known_messages"],
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_message(self, msg: can.Message) -> None:
        now = getattr(msg, "timestamp", None) or time.time()
        arb_id = msg.arbitration_id
        data = bytes(msg.data)

        with self._lock:
            if not self._active:
                return

            self._total_messages += 1
            self._last_message_at = now

            if arb_id not in self._table:
                self._table[arb_id] = {
                    "first_seen": now,
                    "last_seen": now,
                    "count": 1,
                    "dlc": msg.dlc,
                    "last_data": data,
                    "prev_data": None,
                    "history": [{"timestamp": now, "data": data}],
                }
            else:
                entry = self._table[arb_id]
                if entry["last_data"] != data:
                    entry["prev_data"] = entry["last_data"]
                entry["last_data"] = data
                entry["last_seen"] = now
                entry["count"] += 1
                entry["dlc"] = msg.dlc
                entry["history"].append({"timestamp": now, "data": data})
                if len(entry["history"]) > MAX_HISTORY:
                    entry["history"].pop(0)
