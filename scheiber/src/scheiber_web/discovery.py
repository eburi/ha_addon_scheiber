"""Live Bloc9 discovery service for the web app."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

import can

from scheiber.discovery import classify_bloc9_message


class Bloc9DiscoveryService:
    """Observe raw CAN traffic and aggregate Bloc9 discovery candidates."""

    def __init__(self, runtime_controller):
        self.runtime_controller = runtime_controller
        self._lock = threading.RLock()
        self._active = False
        self._session: Optional[Dict[str, Any]] = None

    def start(self) -> Dict[str, Any]:
        """Start or reset discovery. Runs until stop() is called."""
        if not self.runtime_controller.has_live_runtime():
            raise RuntimeError("The bridge must be running before discovery can start")

        with self._lock:
            if self._active:
                self.runtime_controller.unsubscribe_from_messages(self._handle_message)

            now = time.time()
            self._session = {
                "status": "running",
                "started_at": now,
                "last_message_at": None,
                "message_counts": {"state_update": 0, "heartbeat": 0},
                "candidates": {},
            }
            self._active = True
            self.runtime_controller.subscribe_to_messages(self._handle_message)
            return self.snapshot()

    def stop(self) -> Dict[str, Any]:
        """Stop discovery and return the final snapshot."""
        with self._lock:
            if self._active:
                self.runtime_controller.unsubscribe_from_messages(self._handle_message)
            self._active = False
            if self._session is None:
                self._session = self._empty_snapshot("idle")
            else:
                self._session["status"] = "stopped"
            return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable discovery snapshot."""
        with self._lock:
            if self._session is None:
                return self._empty_snapshot("idle")

            candidates = []
            for bus_id, candidate in sorted(self._session["candidates"].items()):
                groups_seen = sorted(candidate["groups_seen"])
                confidence = self._build_confidence(candidate)
                candidates.append(
                    {
                        "bus_id": bus_id,
                        "first_seen_at": candidate["first_seen_at"],
                        "last_seen_at": candidate["last_seen_at"],
                        "groups_seen": groups_seen,
                        "sample_arbitration_ids": candidate["sample_arbitration_ids"],
                        "heartbeat_seen": candidate["heartbeat_seen"],
                        "state_update_count": candidate["state_update_count"],
                        "latest_outputs": candidate["latest_outputs"],
                        "confidence": confidence,
                    }
                )

            return {
                "status": self._session["status"],
                "started_at": self._session["started_at"],
                "last_message_at": self._session["last_message_at"],
                "message_counts": self._session["message_counts"],
                "candidates": candidates,
            }

    def _handle_message(self, msg: can.Message) -> None:
        observation = classify_bloc9_message(msg)
        if observation is None:
            return

        timestamp = getattr(msg, "timestamp", None) or time.time()

        with self._lock:
            if not self._active or self._session is None:
                return

            self._session["last_message_at"] = timestamp
            kind = observation["kind"]
            self._session["message_counts"][kind] += 1

            bus_id = observation["bus_id"]
            candidate = self._session["candidates"].setdefault(
                bus_id,
                {
                    "first_seen_at": timestamp,
                    "last_seen_at": timestamp,
                    "groups_seen": set(),
                    "sample_arbitration_ids": [],
                    "heartbeat_seen": False,
                    "state_update_count": 0,
                    "latest_outputs": {},
                },
            )
            candidate["last_seen_at"] = timestamp

            arbitration_id = observation["arbitration_id"]
            if arbitration_id not in candidate["sample_arbitration_ids"]:
                candidate["sample_arbitration_ids"].append(arbitration_id)
                candidate["sample_arbitration_ids"] = candidate[
                    "sample_arbitration_ids"
                ][:6]

            if kind == "heartbeat":
                candidate["heartbeat_seen"] = True
                return

            candidate["state_update_count"] += 1
            candidate["groups_seen"].add(observation["group"])
            candidate["latest_outputs"].update(observation["outputs"])

    def _build_confidence(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        if candidate["state_update_count"] >= 2 and len(candidate["groups_seen"]) >= 2:
            return {
                "level": "high",
                "score": 100,
                "reasons": [
                    "Multiple authoritative state updates observed",
                    "More than one Bloc9 output group was seen",
                ],
            }
        if candidate["state_update_count"] >= 1:
            return {
                "level": "medium",
                "score": 70,
                "reasons": ["At least one authoritative Bloc9 state update was seen"],
            }
        return {
            "level": "low",
            "score": 30,
            "reasons": ["Only heartbeat traffic has been seen so far"],
        }

    def _empty_snapshot(self, status: str) -> Dict[str, Any]:
        return {
            "status": status,
            "started_at": None,
            "last_message_at": None,
            "message_counts": {"state_update": 0, "heartbeat": 0},
            "candidates": [],
        }
