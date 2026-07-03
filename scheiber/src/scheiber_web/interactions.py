"""Interaction discovery service for button-to-Bloc9 protocol analysis."""

from __future__ import annotations

import copy
import threading
import time
from collections import Counter, deque
from typing import Any, Deque, Dict, List, Optional

import can

from scheiber.button_discovery import (
    classify_button_source_message,
    diff_status_bits,
)
from scheiber.discovery import classify_bloc9_message


class InteractionDiscoveryService:
    """Capture probable button-source messages and correlated Bloc9 reactions."""

    BUFFER_SECONDS = 5.0
    REACTION_SECONDS = 10.0

    def __init__(self, runtime_controller):
        self.runtime_controller = runtime_controller
        self._lock = threading.RLock()
        self._subscribed = False
        self._active = False
        self._session: Optional[Dict[str, Any]] = None
        self._recent_messages: Deque[Dict[str, Any]] = deque()
        self._latest_outputs: Dict[str, Dict[str, Any]] = {}
        self._button_states: Dict[str, Dict[str, Any]] = {}

    def start(self, location: str) -> Dict[str, Any]:
        if not self.runtime_controller.has_live_runtime():
            raise RuntimeError(
                "The bridge must be running before interaction discovery can start"
            )

        cleaned_location = str(location or "").strip()
        if not cleaned_location:
            raise ValueError("location is required")

        with self._lock:
            self._ensure_subscription()
            now = time.time()
            self._active = True
            self._recent_messages.clear()
            self._session = {
                "status": "running",
                "phase": "waiting_for_button",
                "location": cleaned_location,
                "started_at": now,
                "last_message_at": None,
                "reaction_started_at": None,
                "reaction_deadline_at": None,
                "message_counts": {
                    "button_source_status": 0,
                    "bloc9_state_update": 0,
                    "bloc9_heartbeat": 0,
                    "other": 0,
                },
                "button_events": [],
                "button_candidates": {},
                "reaction_outputs": {},
                "raw_context": [],
                "other_messages": Counter(),
                "other_samples": {},
                "baseline_outputs": copy.deepcopy(self._latest_outputs),
            }
            return self.snapshot()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self._active = False
            if self._session is not None:
                self._session["status"] = "stopped"
                if self._session.get("phase") not in {"complete", "idle"}:
                    self._session["phase"] = "stopped"
            return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            self._advance_if_needed()
            if self._session is None:
                return self._empty_snapshot()

            session = self._session
            return {
                "status": session["status"],
                "phase": session["phase"],
                "location": session["location"],
                "started_at": session["started_at"],
                "last_message_at": session["last_message_at"],
                "reaction_started_at": session["reaction_started_at"],
                "reaction_deadline_at": session["reaction_deadline_at"],
                "remaining_reaction_seconds": self._remaining_reaction_seconds(session),
                "message_counts": dict(session["message_counts"]),
                "button_events": list(session["button_events"][-20:]),
                "button_candidates": self._button_candidate_snapshot(session),
                "reaction_outputs": self._reaction_output_snapshot(session),
                "raw_context": list(session["raw_context"][-40:]),
                "other_messages": [
                    {
                        "arbitration_id": arbitration_id,
                        "count": count,
                        "sample_data": session["other_samples"].get(arbitration_id, ""),
                    }
                    for arbitration_id, count in session["other_messages"].most_common(10)
                ],
                "hypothesis": self._hypothesis_snapshot(session),
            }

    def _ensure_subscription(self) -> None:
        if self._subscribed:
            return
        self.runtime_controller.subscribe_to_messages(self._handle_message)
        self._subscribed = True

    def _handle_message(self, msg: can.Message) -> None:
        timestamp = getattr(msg, "timestamp", None) or time.time()
        button_observation = classify_button_source_message(msg)
        bloc9_observation = classify_bloc9_message(msg)
        raw_entry = self._raw_entry(msg, timestamp, button_observation, bloc9_observation)

        with self._lock:
            self._remember_recent(raw_entry, timestamp)
            if bloc9_observation is not None and bloc9_observation["kind"] == "state_update":
                self._update_latest_outputs(bloc9_observation, timestamp)

            if not self._active or self._session is None:
                return

            session = self._session
            session["last_message_at"] = timestamp
            if session["phase"] != "waiting_for_button":
                session["raw_context"].append(raw_entry)
                session["raw_context"] = session["raw_context"][-80:]

            if button_observation is not None:
                session["message_counts"]["button_source_status"] += 1
                self._record_button_observation(session, button_observation, timestamp)
                return

            if bloc9_observation is not None:
                if bloc9_observation["kind"] == "heartbeat":
                    session["message_counts"]["bloc9_heartbeat"] += 1
                    return

                session["message_counts"]["bloc9_state_update"] += 1
                self._record_bloc9_observation(session, bloc9_observation, timestamp)
                return

            session["message_counts"]["other"] += 1
            arbitration_id = f"0x{msg.arbitration_id:08X}"
            session["other_messages"][arbitration_id] += 1
            session["other_samples"].setdefault(arbitration_id, msg.data.hex().upper())

    def _remember_recent(self, entry: Dict[str, Any], timestamp: float) -> None:
        self._recent_messages.append(entry)
        cutoff = timestamp - self.BUFFER_SECONDS
        while self._recent_messages and self._recent_messages[0]["timestamp"] < cutoff:
            self._recent_messages.popleft()

    def _raw_entry(
        self,
        msg: can.Message,
        timestamp: float,
        button_observation: Optional[Dict[str, Any]],
        bloc9_observation: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        kind = "other"
        if button_observation is not None:
            kind = "button_source_status"
        elif bloc9_observation is not None:
            kind = f"bloc9_{bloc9_observation['kind']}"
        return {
            "timestamp": timestamp,
            "arbitration_id": f"0x{msg.arbitration_id:08X}",
            "data": msg.data.hex().upper(),
            "kind": kind,
        }

    def _record_button_observation(
        self,
        session: Dict[str, Any],
        observation: Dict[str, Any],
        timestamp: float,
    ) -> None:
        if session["phase"] == "waiting_for_button":
            session["phase"] = "waiting_for_bloc9_change"
            session["raw_context"] = list(self._recent_messages)

        previous = self._button_states.get(observation["candidate_key"])
        previous_status = previous["status_byte"] if previous else None
        transitions = (
            diff_status_bits(previous_status, observation["status_byte"])
            if previous_status is not None
            else {"rising_bits": [], "falling_bits": []}
        )
        event_type = self._button_event_type(observation, previous_status, transitions)

        event = {
            "timestamp": timestamp,
            "event_type": event_type,
            "arbitration_id": observation["arbitration_id"],
            "source_family": observation["source_family"],
            "candidate_key": observation["candidate_key"],
            "identity_hex": observation["identity_hex"],
            "status_hex": observation["status_hex"],
            "active_bits": observation["active_bits"],
            "lower_active_bits": observation["lower_active_bits"],
            "high_bit_set": observation["high_bit_set"],
            "rising_bits": transitions["rising_bits"],
            "falling_bits": transitions["falling_bits"],
            "data_hex": observation["data_hex"],
            "confidence": observation["confidence"],
        }
        session["button_events"].append(event)

        candidate = session["button_candidates"].setdefault(
            observation["candidate_key"],
            {
                "candidate_key": observation["candidate_key"],
                "arbitration_id": observation["arbitration_id"],
                "source_family": observation["source_family"],
                "identity_hex": observation["identity_hex"],
                "first_seen_at": timestamp,
                "last_seen_at": timestamp,
                "event_count": 0,
                "statuses_seen": {},
                "rising_bits": Counter(),
                "falling_bits": Counter(),
                "sample_data": [],
                "confidence": observation["confidence"],
            },
        )
        candidate["last_seen_at"] = timestamp
        candidate["event_count"] += 1
        candidate["statuses_seen"][observation["status_hex"]] = observation["data_hex"]
        for bit in transitions["rising_bits"]:
            candidate["rising_bits"][bit] += 1
        for bit in transitions["falling_bits"]:
            candidate["falling_bits"][bit] += 1
        if observation["data_hex"] not in candidate["sample_data"]:
            candidate["sample_data"].append(observation["data_hex"])
            candidate["sample_data"] = candidate["sample_data"][:6]

        self._button_states[observation["candidate_key"]] = {
            "status_byte": observation["status_byte"],
            "timestamp": timestamp,
        }

    def _record_bloc9_observation(
        self,
        session: Dict[str, Any],
        observation: Dict[str, Any],
        timestamp: float,
    ) -> None:
        if session["phase"] in {"waiting_for_button", "waiting_for_bloc9_change"}:
            session["phase"] = "waiting_for_reaction"
            session["reaction_started_at"] = timestamp
            session["reaction_deadline_at"] = timestamp + self.REACTION_SECONDS
            if not session["raw_context"]:
                session["raw_context"] = list(self._recent_messages)

        if session["phase"] not in {"waiting_for_reaction", "complete"}:
            return

        if (
            session["reaction_started_at"] is not None
            and timestamp > session["reaction_deadline_at"]
        ):
            self._complete_session(session)
            return

        for output_name, sample in observation["outputs"].items():
            output_ref = f"{observation['route_slug']}:{output_name}"
            baseline = session["baseline_outputs"].get(output_ref, {}).get("sample")
            reaction = session["reaction_outputs"].setdefault(
                output_ref,
                {
                    "output_ref": output_ref,
                    "bus_id": observation["bus_id"],
                    "segment_id": observation["segment_id"],
                    "route_slug": observation["route_slug"],
                    "output_name": output_name,
                    "baseline": baseline,
                    "first_seen_at": timestamp,
                    "last_seen_at": timestamp,
                    "message_count": 0,
                    "samples": [],
                },
            )
            reaction["last_seen_at"] = timestamp
            reaction["message_count"] += 1
            if not reaction["samples"] or reaction["samples"][-1] != sample:
                reaction["samples"].append(sample)
                reaction["samples"] = reaction["samples"][-12:]

    def _update_latest_outputs(
        self, observation: Dict[str, Any], timestamp: float
    ) -> None:
        for output_name, sample in observation["outputs"].items():
            output_ref = f"{observation['route_slug']}:{output_name}"
            self._latest_outputs[output_ref] = {
                "bus_id": observation["bus_id"],
                "segment_id": observation["segment_id"],
                "route_slug": observation["route_slug"],
                "output_name": output_name,
                "sample": sample,
                "last_seen_at": timestamp,
            }

    def _advance_if_needed(self) -> None:
        if not self._active or self._session is None:
            return
        session = self._session
        deadline = session.get("reaction_deadline_at")
        if deadline is not None and time.time() >= deadline:
            self._complete_session(session)

    def _complete_session(self, session: Dict[str, Any]) -> None:
        session["status"] = "complete"
        session["phase"] = "complete"
        self._active = False

    def _button_event_type(
        self,
        observation: Dict[str, Any],
        previous_status: Optional[int],
        transitions: Dict[str, List[int]],
    ) -> str:
        if previous_status is None:
            return "initial_pressed" if observation["high_bit_set"] else "initial_released"
        if transitions["rising_bits"] and observation["high_bit_set"]:
            return "key_down"
        if transitions["falling_bits"] and not observation["high_bit_set"]:
            return "key_up"
        if observation["high_bit_set"]:
            return "pressed_status"
        return "released_status"

    def _button_candidate_snapshot(self, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates = []
        for candidate in session["button_candidates"].values():
            candidates.append(
                {
                    "candidate_key": candidate["candidate_key"],
                    "arbitration_id": candidate["arbitration_id"],
                    "source_family": candidate["source_family"],
                    "identity_hex": candidate["identity_hex"],
                    "first_seen_at": candidate["first_seen_at"],
                    "last_seen_at": candidate["last_seen_at"],
                    "event_count": candidate["event_count"],
                    "statuses_seen": [
                        {"status_hex": status, "sample_data": sample}
                        for status, sample in sorted(candidate["statuses_seen"].items())
                    ],
                    "rising_bits": [
                        {"bit": bit, "count": count}
                        for bit, count in candidate["rising_bits"].most_common()
                    ],
                    "falling_bits": [
                        {"bit": bit, "count": count}
                        for bit, count in candidate["falling_bits"].most_common()
                    ],
                    "sample_data": list(candidate["sample_data"]),
                    "confidence": candidate["confidence"],
                }
            )
        return sorted(
            candidates, key=lambda item: (item["arbitration_id"], item["identity_hex"])
        )

    def _reaction_output_snapshot(self, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        outputs = []
        for output in session["reaction_outputs"].values():
            samples = output["samples"]
            baseline = output["baseline"]
            final = samples[-1] if samples else None
            brightness_values = {
                sample.get("effective_brightness")
                for sample in samples
                if sample.get("state") is True
            }
            changed = (
                baseline != final
                or len({self._sample_key(sample) for sample in samples}) > 1
            )
            if not changed:
                continue
            outputs.append(
                {
                    **output,
                    "current": final,
                    "sample_count": len(samples),
                    "dimming_observed": len(brightness_values) > 1,
                }
            )
        return sorted(
            outputs,
            key=lambda item: (item["route_slug"], item["output_name"]),
        )

    def _hypothesis_snapshot(self, session: Dict[str, Any]) -> Dict[str, Any]:
        button_count = len(session["button_candidates"])
        output_count = len(self._reaction_output_snapshot(session))
        if button_count and output_count:
            confidence = "medium"
            summary = "Button-source status frames and Bloc9 output reactions were both captured."
        elif button_count:
            confidence = "low"
            summary = "Button-source status frames were captured, but no Bloc9 reaction was observed yet."
        elif output_count:
            confidence = "low"
            summary = "Bloc9 output reactions were captured before a decoded button-source candidate was seen."
        else:
            confidence = "unknown"
            summary = "No useful interaction evidence has been captured yet."
        return {
            "confidence": confidence,
            "summary": summary,
            "notes": [
                "Known local captures use 0x04001A80 for the 2.4 GHz wireless interface and 0x04001808 for a panel or key interface.",
                "The classifier treats payload bytes before the final status byte as observed identity bytes, not a proven global address schema.",
                "The final status byte appears bitwise encoded; bit 7 commonly marks pressed status in captured wireless examples.",
            ],
        }

    def _remaining_reaction_seconds(self, session: Dict[str, Any]) -> Optional[int]:
        deadline = session.get("reaction_deadline_at")
        if deadline is None or session.get("status") != "running":
            return None
        return max(0, int(round(deadline - time.time())))

    def _sample_key(self, sample: Dict[str, Any]) -> tuple:
        return (
            sample.get("state"),
            sample.get("raw_brightness"),
            sample.get("effective_brightness"),
        )

    def _empty_snapshot(self) -> Dict[str, Any]:
        return {
            "status": "idle",
            "phase": "idle",
            "location": "",
            "started_at": None,
            "last_message_at": None,
            "reaction_started_at": None,
            "reaction_deadline_at": None,
            "remaining_reaction_seconds": None,
            "message_counts": {
                "button_source_status": 0,
                "bloc9_state_update": 0,
                "bloc9_heartbeat": 0,
                "other": 0,
            },
            "button_events": [],
            "button_candidates": [],
            "reaction_outputs": [],
            "raw_context": [],
            "other_messages": [],
            "hypothesis": {
                "confidence": "unknown",
                "summary": "Start discovery and press a physical button to capture evidence.",
                "notes": [],
            },
        }
