"""Guided capture of Scheiber wireless Air Switch (SFSP) button presses.

Scheiber calls this hardware "Light Air Switch"; the boat's own French
labelling is "Sans Fil Sans Pile" (SFSP, i.e. "no wires, no battery").
Physical units are mounted in a Vimar frame and come in two shapes:

- Two-function: a single rocker, divided horizontally into a top button and
  a bottom button.
- Four-function: two rockers side by side (divided vertically from each
  other), each of which is also divided horizontally into a top and bottom
  button, giving four independent functions (top-left, bottom-left,
  top-right, bottom-right).

This service walks an operator through a structured capture: enter a
location and the unit's function count, then press-and-release each
function several times while every button-source CAN frame and any
resulting Bloc9/panel reaction is recorded. Finished sessions are appended
to a JSON Lines log file so that data collected across many different
physical units (and the multiple wireless receivers installed on the boat)
can be analyzed offline for patterns: is the same bit layout used across
units, and how does the CAN bus avoid duplicate reports when more than one
receiver hears the same press?

This is intentionally scoped to the wireless Air Switch/SFSP family only.
Wired panel buttons (which also carry state-indicator lights) are a
separate, deferred investigation, though their CAN traffic may still be
captured here as a *reaction* when a wireless press changes a light that a
panel also reflects.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import can

from scheiber.button_discovery import (
    classify_air_switch_message,
    classify_button_source_message,
)
from scheiber.discovery import classify_bloc9_message

logger = logging.getLogger(__name__)

# Ordered function sequences an operator is guided through, keyed by how
# many individual functions the physical Vimar unit provides.
STEP_SEQUENCES: Dict[int, List[Dict[str, str]]] = {
    2: [
        {
            "key": "top",
            "label": "Top",
            "instruction": "Press and release the TOP button several times (aim for 5+ presses).",
        },
        {
            "key": "bottom",
            "label": "Bottom",
            "instruction": "Press and release the BOTTOM button several times (aim for 5+ presses).",
        },
    ],
    4: [
        {
            "key": "top_left",
            "label": "Top Left",
            "instruction": "Press and release the TOP-LEFT button several times (aim for 5+ presses).",
        },
        {
            "key": "bottom_left",
            "label": "Bottom Left",
            "instruction": "Press and release the BOTTOM-LEFT button several times (aim for 5+ presses).",
        },
        {
            "key": "top_right",
            "label": "Top Right",
            "instruction": "Press and release the TOP-RIGHT button several times (aim for 5+ presses).",
        },
        {
            "key": "bottom_right",
            "label": "Bottom Right",
            "instruction": "Press and release the BOTTOM-RIGHT button several times (aim for 5+ presses).",
        },
    ],
}

# The confirmed wireless Air Switch family (see
# plan/button-interaction-hypothesis.md) plus its unconfirmed companion
# messages (e.g. 0x0402xxxx/0x0408xxxx) all live under this prefix. Capturing
# the whole family, not just the 5-byte button-status shape, keeps evidence
# useful for investigating how multiple wireless receivers avoid duplicate
# reports.
AIR_SWITCH_FAMILY_PREFIX = 0x04000000
AIR_SWITCH_FAMILY_MASK = 0xFF000000


def _slugify_entity_id(value: str) -> str:
    """Slugify free-text into an entity-id-safe string (lowercase, underscores)."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return slug.strip("_")


class InteractionDiscoveryService:
    """Guide an operator through capturing one physical Air Switch unit."""

    def __init__(
        self,
        runtime_controller,
        log_file_path: Optional[str] = None,
    ):
        self.runtime_controller = runtime_controller
        self.log_file_path = log_file_path
        self._lock = threading.RLock()
        self._subscribed = False
        self._session: Optional[Dict[str, Any]] = None

    def start(self, location: str, button_count: Any) -> Dict[str, Any]:
        if not self.runtime_controller.has_live_runtime():
            raise RuntimeError(
                "The bridge must be running before interaction discovery can start"
            )

        cleaned_location = str(location or "").strip()
        if not cleaned_location:
            raise ValueError("location is required")

        try:
            normalized_button_count = int(button_count)
        except (TypeError, ValueError):
            normalized_button_count = None
        if normalized_button_count not in STEP_SEQUENCES:
            raise ValueError("button_count must be 2 or 4")

        with self._lock:
            self._ensure_subscription()
            now = time.time()
            self._session = {
                "status": "running",
                "location": cleaned_location,
                "button_count": normalized_button_count,
                "started_at": now,
                "last_message_at": None,
                "current_step_index": 0,
                "steps": [
                    {
                        "key": step["key"],
                        "label": step["label"],
                        "instruction": step["instruction"],
                        "events": [],
                        "reactions": [],
                        "companion_frames": [],
                    }
                    for step in STEP_SEQUENCES[normalized_button_count]
                ],
                "saved_at": None,
                "saved_path": None,
            }
            return self.snapshot()

    def next_step(self) -> Dict[str, Any]:
        with self._lock:
            session = self._require_active_session()
            if session["current_step_index"] >= len(session["steps"]) - 1:
                raise ValueError("Already on the last step; use finish instead")
            session["current_step_index"] += 1
            return self.snapshot()

    def previous_step(self) -> Dict[str, Any]:
        with self._lock:
            session = self._require_active_session()
            if session["current_step_index"] <= 0:
                raise ValueError("Already on the first step")
            session["current_step_index"] -= 1
            return self.snapshot()

    def finish(self) -> Dict[str, Any]:
        with self._lock:
            session = self._require_active_session()
            session["status"] = "complete"
            self._save_session(session)
            return self.snapshot()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if self._session is not None and self._session["status"] == "running":
                self._session["status"] = "stopped"
            return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            if self._session is None:
                return self._empty_snapshot()

            session = self._session
            steps_summary = [
                self._step_summary(session, step) for step in session["steps"]
            ]
            current_index = session["current_step_index"]

            return {
                "status": session["status"],
                "location": session["location"],
                "button_count": session["button_count"],
                "started_at": session["started_at"],
                "last_message_at": session["last_message_at"],
                "current_step_index": current_index,
                "current_step": steps_summary[current_index] if steps_summary else None,
                "is_first_step": current_index <= 0,
                "is_last_step": current_index >= len(steps_summary) - 1,
                "steps": steps_summary,
                "saved_at": session["saved_at"],
                "saved_path": session["saved_path"],
            }

    def recent_sessions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return summaries of the most recently saved sessions, if any."""
        if not self.log_file_path or not os.path.exists(self.log_file_path):
            return []

        try:
            with open(self.log_file_path, "r", encoding="utf-8") as handle:
                lines = [line for line in handle if line.strip()]
        except OSError as exc:
            logger.error(f"Failed to read interactions log: {exc}")
            return []

        summaries = []
        for line in lines[-limit:]:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            steps = record.get("steps", [])
            summaries.append(
                {
                    "saved_at": record.get("saved_at"),
                    "location": record.get("location"),
                    "button_count": record.get("button_count"),
                    "total_events": sum(len(step.get("events", [])) for step in steps),
                    "total_reactions": sum(
                        len(step.get("reactions", [])) for step in steps
                    ),
                }
            )
        return summaries

    def _require_active_session(self) -> Dict[str, Any]:
        if self._session is None:
            raise RuntimeError("No interaction session is active; start one first")
        return self._session

    def _ensure_subscription(self) -> None:
        if self._subscribed:
            return
        self.runtime_controller.subscribe_to_messages(self._handle_message)
        self._subscribed = True

    def _handle_message(self, msg: can.Message) -> None:
        timestamp = getattr(msg, "timestamp", None) or time.time()

        with self._lock:
            session = self._session
            if session is None or session["status"] != "running":
                return

            step = session["steps"][session["current_step_index"]]

            button_observation = classify_button_source_message(msg)
            if button_observation is not None:
                session["last_message_at"] = timestamp
                air_switch_observation = classify_air_switch_message(msg)
                step["events"].append(
                    {
                        "timestamp": timestamp,
                        "arbitration_id": button_observation["arbitration_id"],
                        "data_hex": button_observation["data_hex"],
                        "source_family": button_observation["source_family"],
                        "status_hex": button_observation["status_hex"],
                        "confirmed_air_switch": air_switch_observation,
                    }
                )
                return

            bloc9_observation = classify_bloc9_message(msg)
            if (
                bloc9_observation is not None
                and bloc9_observation["kind"] == "state_update"
            ):
                session["last_message_at"] = timestamp
                step["reactions"].append(
                    {
                        "timestamp": timestamp,
                        "arbitration_id": bloc9_observation["arbitration_id"],
                        "route_slug": bloc9_observation["route_slug"],
                        "bus_id": bloc9_observation["bus_id"],
                        "segment_id": bloc9_observation["segment_id"],
                        "outputs": bloc9_observation["outputs"],
                    }
                )
                return

            if (
                msg.arbitration_id & AIR_SWITCH_FAMILY_MASK
            ) == AIR_SWITCH_FAMILY_PREFIX:
                # Unconfirmed companion traffic (e.g. 0x0402xxxx/0x0408xxxx)
                # that reliably accompanies button events but whose meaning
                # isn't decoded yet; kept for offline pattern analysis.
                session["last_message_at"] = timestamp
                step["companion_frames"].append(
                    {
                        "timestamp": timestamp,
                        "arbitration_id": f"0x{msg.arbitration_id:08X}",
                        "data_hex": bytes(msg.data).hex().upper(),
                    }
                )

    def _step_summary(
        self, session: Dict[str, Any], step: Dict[str, Any]
    ) -> Dict[str, Any]:
        confirmed = self._step_confirmed_summary(step)
        return {
            "key": step["key"],
            "label": step["label"],
            "instruction": step["instruction"],
            "event_count": len(step["events"]),
            "reaction_count": len(step["reactions"]),
            "companion_count": len(step["companion_frames"]),
            "recent_events": step["events"][-10:],
            "recent_reactions": step["reactions"][-10:],
            "confirmed_air_switch": confirmed,
            "suggested_config": self._suggested_config(session, step, confirmed),
        }

    def _step_confirmed_summary(self, step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return the most common confirmed (identity, button_index) pair, if any."""
        counts: Dict[Any, int] = {}
        for event in step["events"]:
            confirmed = event.get("confirmed_air_switch")
            if confirmed is None:
                continue
            key = (confirmed["identity_hex"], confirmed["button_index"])
            counts[key] = counts.get(key, 0) + 1

        if not counts:
            return None

        (identity_hex, button_index), occurrences = max(
            counts.items(), key=lambda item: item[1]
        )
        return {
            "identity_hex": identity_hex,
            "button_index": button_index,
            "occurrences": occurrences,
            "distinct_pairs_seen": len(counts),
        }

    def _suggested_config(
        self,
        session: Dict[str, Any],
        step: Dict[str, Any],
        confirmed: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if confirmed is None:
            return None

        location = str(session.get("location") or "").strip()
        location_slug = _slugify_entity_id(location) or "air_switch"
        step_slug = _slugify_entity_id(step["label"])
        name = f"{location.title()} {step['label']}" if location else step["label"]
        entity_id = f"{location_slug}_{step_slug}"

        return {
            "name": name,
            "entity_id": entity_id,
            "identity": confirmed["identity_hex"],
            "button_index": confirmed["button_index"],
            "yaml": (
                "- name: "
                + _yaml_quote(name)
                + "\n  entity_id: "
                + entity_id
                + "\n  identity: "
                + _yaml_quote(confirmed["identity_hex"])
                + "\n  button_index: "
                + str(confirmed["button_index"])
            ),
        }

    def _save_session(self, session: Dict[str, Any]) -> None:
        if not self.log_file_path:
            session["saved_at"] = None
            session["saved_path"] = None
            return

        record = {
            "saved_at": time.time(),
            "location": session["location"],
            "button_count": session["button_count"],
            "started_at": session["started_at"],
            "steps": [
                {
                    "key": step["key"],
                    "label": step["label"],
                    "events": step["events"],
                    "reactions": step["reactions"],
                    "companion_frames": step["companion_frames"],
                }
                for step in session["steps"]
            ],
        }

        try:
            path = Path(self.log_file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
            session["saved_at"] = record["saved_at"]
            session["saved_path"] = str(path)
        except OSError as exc:
            logger.error(f"Failed to write interactions log: {exc}")
            session["saved_at"] = None
            session["saved_path"] = None

    def _empty_snapshot(self) -> Dict[str, Any]:
        return {
            "status": "idle",
            "location": "",
            "button_count": None,
            "started_at": None,
            "last_message_at": None,
            "current_step_index": 0,
            "current_step": None,
            "is_first_step": True,
            "is_last_step": False,
            "steps": [],
            "saved_at": None,
            "saved_path": None,
        }


def _yaml_quote(value: str) -> str:
    """Render a double-quoted YAML scalar, escaping backslashes and quotes."""
    escaped = str(value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
