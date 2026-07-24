"""Persistent AirSwitch discovery service for the setup UI.

This service watches confirmed wireless AirSwitch frames continuously while
enabled by the user. Discovery is intentionally independent of browser
sessions: it is not stopped by frontend idle cleanup, and its accumulated
state is persisted to the add-on data directory.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import can

from scheiber.button_discovery import classify_air_switch_message

logger = logging.getLogger(__name__)


class AirSwitchDiscoveryService:
    """Continuously discover wireless AirSwitch identities and indexes."""

    def __init__(self, runtime_controller, state_file_path: Optional[str] = None):
        self.runtime_controller = runtime_controller
        self.state_file_path = state_file_path
        self._lock = threading.RLock()
        self._subscribed = False
        self._state = self._load_state()

    def start(self) -> Dict[str, Any]:
        if not self.runtime_controller.has_live_runtime():
            raise RuntimeError(
                "The bridge must be running before AirSwitch discovery can start"
            )
        with self._lock:
            self._ensure_subscription()
            self._state["running"] = True
            self._state["updated_at"] = time.time()
            self._save_state_locked()
            return self.snapshot()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self._state["running"] = False
            self._state["updated_at"] = time.time()
            self._save_state_locked()
            return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            switches = []
            for identity, entry in sorted(self._state.get("air_switches", {}).items()):
                indexes = []
                for index, index_entry in sorted(
                    entry.get("indexes", {}).items(), key=lambda item: int(item[0])
                ):
                    indexes.append(
                        {
                            "index": int(index),
                            "default_label": default_index_label(
                                entry.get("indexes", {}), int(index)
                            ),
                            **copy.deepcopy(index_entry),
                        }
                    )
                switches.append({**copy.deepcopy(entry), "indexes": indexes})
            return {
                "running": bool(self._state.get("running", False)),
                "updated_at": self._state.get("updated_at"),
                "air_switches": switches,
                "state_file_path": self.state_file_path,
            }

    def _ensure_subscription(self) -> None:
        if self._subscribed:
            return
        self.runtime_controller.subscribe_to_messages(self._handle_message)
        self._subscribed = True

    def _handle_message(self, msg: can.Message) -> None:
        observation = classify_air_switch_message(msg)
        if observation is None:
            return

        with self._lock:
            if not self._state.get("running", False):
                return
            now = getattr(msg, "timestamp", None) or time.time()
            identity = observation["identity_hex"]
            index = str(observation["button_index"])
            air_switches = self._state.setdefault("air_switches", {})
            entry = air_switches.setdefault(
                identity,
                {
                    "identity": identity,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "can_ids": {},
                    "indexes": {},
                },
            )
            entry["last_seen_at"] = now
            can_id = observation["arbitration_id"]
            entry["can_ids"][can_id] = entry["can_ids"].get(can_id, 0) + 1

            index_entry = entry["indexes"].setdefault(
                index,
                {
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "press_count": 0,
                    "release_count": 0,
                    "last_status_hex": None,
                },
            )
            index_entry["last_seen_at"] = now
            index_entry["last_status_hex"] = observation["status_hex"]
            if observation["pressed"]:
                index_entry["press_count"] += 1
            else:
                index_entry["release_count"] += 1
            self._state["updated_at"] = now
            self._save_state_locked()

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_file_path or not os.path.exists(self.state_file_path):
            return {"running": False, "updated_at": None, "air_switches": {}}
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError("state root is not an object")
            loaded.setdefault("running", False)
            loaded.setdefault("updated_at", None)
            loaded.setdefault("air_switches", {})
            return loaded
        except Exception as exc:
            logger.error(f"Failed to load AirSwitch discovery state: {exc}")
            return {"running": False, "updated_at": None, "air_switches": {}}

    def _save_state_locked(self) -> None:
        if not self.state_file_path:
            return
        try:
            path = Path(self.state_file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_suffix(f"{path.suffix}.tmp")
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(self._state, handle, indent=2, sort_keys=True)
            os.replace(temp_path, path)
        except OSError as exc:
            logger.error(f"Failed to save AirSwitch discovery state: {exc}")


def default_index_label(indexes: Dict[str, Any], index: int) -> str:
    seen = {int(value) for value in indexes.keys() if str(value).isdigit()}
    if {1, 2, 3, 4}.issubset(seen):
        return {
            1: "Bottom Left",
            2: "Top Left",
            3: "Bottom Right",
            4: "Top Right",
        }.get(index, f"Index {index}")
    if {1, 2}.issubset(seen):
        return {1: "Bottom", 2: "Top"}.get(index, f"Index {index}")
    return f"Index {index}"
