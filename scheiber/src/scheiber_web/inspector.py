"""CAN Bus Inspector service for reverse engineering and protocol discovery."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

import can


MAX_HISTORY = 30


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
