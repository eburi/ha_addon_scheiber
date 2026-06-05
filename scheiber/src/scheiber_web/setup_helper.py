"""Interactive setup-helper service for guided Bloc9 discovery."""

from __future__ import annotations

import copy
import math
import threading
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

import can

from scheiber.discovery import classify_bloc9_message


class SetupHelperService:
    """Guide the operator through repeatable button-driven discovery."""

    def __init__(self, runtime_controller):
        self.runtime_controller = runtime_controller
        self._lock = threading.RLock()
        self._subscribed = False
        self._known_outputs: Dict[str, Dict[str, Any]] = {}
        self._session: Optional[Dict[str, Any]] = None

    def start_session(
        self,
        name: str,
        *,
        entity_id: Optional[str] = None,
        role: str = "light",
    ) -> Dict[str, Any]:
        if not self.runtime_controller.has_live_runtime():
            raise RuntimeError("The bridge must be running before setup helper can start")

        cleaned_name = str(name or "").strip()
        if not cleaned_name:
            raise ValueError("name is required")

        cleaned_role = str(role or "light").strip().lower()
        if cleaned_role not in {"light", "switch"}:
            raise ValueError("role must be 'light' or 'switch'")

        with self._lock:
            self._ensure_subscription()
            self._session = {
                "status": "ready",
                "target_name": cleaned_name,
                "entity_id": str(entity_id or "").strip() or None,
                "target_role": cleaned_role,
                "created_at": time.time(),
                "active_run": None,
                "completed_run": None,
                "evidence": {},
                "run_history": [],
            }
            return self.snapshot()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if self._subscribed:
                self.runtime_controller.unsubscribe_from_messages(self._handle_message)
                self._subscribed = False
            self._session = None
            return self._empty_snapshot()

    def arm_run(self, action: str) -> Dict[str, Any]:
        with self._lock:
            if self._session is None:
                raise RuntimeError("Start a setup helper session first")

            now = time.time()
            normalized_action = str(action or "").strip().lower()
            if normalized_action not in {"tap", "hold"}:
                raise ValueError("action must be 'tap' or 'hold'")

            press_at = now + 5.0
            if normalized_action == "tap":
                release_at = press_at
                capture_end_at = press_at + 3.0
            else:
                release_at = press_at + 4.0
                capture_end_at = release_at + 1.5

            self._session["status"] = "running"
            self._session["active_run"] = {
                "action": normalized_action,
                "started_at": now,
                "press_at": press_at,
                "release_at": release_at,
                "capture_start_at": press_at - 0.25,
                "capture_end_at": capture_end_at,
                "baseline_outputs": copy.deepcopy(self._known_outputs),
                "captured_messages": [],
            }
            return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            self._advance_run_if_needed()
            if self._session is None:
                return self._empty_snapshot()

            active_run = self._session.get("active_run")
            completed_run = self._session.get("completed_run")

            payload = {
                "status": self._session["status"],
                "target_name": self._session["target_name"],
                "entity_id": self._session["entity_id"],
                "target_role": self._session["target_role"],
                "created_at": self._session["created_at"],
                "known_output_count": len(self._known_outputs),
                "phase": "ready",
                "instruction": "Choose a guided action to begin discovery.",
                "active_run": None,
                "completed_run": completed_run,
            }

            if active_run is not None:
                payload["phase"] = self._phase_for_run(active_run)
                payload["instruction"] = self._instruction_for_run(active_run)
                payload["active_run"] = {
                    "action": active_run["action"],
                    "started_at": active_run["started_at"],
                    "press_at": active_run["press_at"],
                    "release_at": active_run["release_at"],
                    "capture_end_at": active_run["capture_end_at"],
                    "countdown": self._countdown_for_run(active_run),
                    "captured_message_count": len(active_run["captured_messages"]),
                }

            return payload

    def _ensure_subscription(self) -> None:
        if self._subscribed:
            return
        self.runtime_controller.subscribe_to_messages(self._handle_message)
        self._subscribed = True

    def _handle_message(self, msg: can.Message) -> None:
        observation = classify_bloc9_message(msg)
        timestamp = getattr(msg, "timestamp", None) or time.time()

        with self._lock:
            if observation is not None and observation["kind"] == "state_update":
                for output_name, sample in observation["outputs"].items():
                    ref = self._output_ref(
                        observation["bus_id"],
                        observation["segment_id"],
                        output_name,
                    )
                    self._known_outputs[ref] = {
                        "bus_id": observation["bus_id"],
                        "segment_id": observation["segment_id"],
                        "route_slug": observation["route_slug"],
                        "output_name": output_name,
                        "sample": sample,
                        "last_seen_at": timestamp,
                    }

            active_run = self._session.get("active_run") if self._session else None
            if active_run is None:
                return

            if not (
                active_run["capture_start_at"] <= timestamp <= active_run["capture_end_at"]
            ):
                return

            entry = {
                "timestamp": timestamp,
                "arbitration_id": f"0x{msg.arbitration_id:08X}",
                "data": msg.data.hex().upper(),
                "kind": observation["kind"] if observation is not None else "other",
            }
            if observation is not None:
                entry["route_slug"] = observation.get("route_slug")
                entry["outputs"] = observation.get("outputs")
            active_run["captured_messages"].append(entry)

    def _advance_run_if_needed(self) -> None:
        if self._session is None:
            return

        active_run = self._session.get("active_run")
        if active_run is None:
            return

        if time.time() < active_run["capture_end_at"]:
            return

        completed = self._analyze_run(active_run)
        self._session["active_run"] = None
        self._session["completed_run"] = completed
        self._session["status"] = "complete"
        self._session["run_history"].append(
            {
                "action": completed["action"],
                "changed_output_refs": [
                    output["output_ref"] for output in completed["changed_outputs"]
                ],
            }
        )

    def _analyze_run(self, run: Dict[str, Any]) -> Dict[str, Any]:
        output_series: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        other_messages: Counter = Counter()
        other_samples: Dict[str, str] = {}

        for entry in run["captured_messages"]:
            if entry["kind"] == "state_update" and entry.get("outputs") and entry.get(
                "route_slug"
            ):
                for output_name, sample in entry["outputs"].items():
                    ref = self._output_ref_from_slug(entry["route_slug"], output_name)
                    output_series[ref].append(sample)
            elif entry["kind"] == "other":
                other_messages[entry["arbitration_id"]] += 1
                other_samples.setdefault(entry["arbitration_id"], entry["data"])

        changed_outputs = []
        baseline_outputs = run["baseline_outputs"]
        all_refs = sorted(
            set(baseline_outputs.keys())
            | set(self._known_outputs.keys())
            | set(output_series.keys())
        )

        for ref in all_refs:
            baseline = baseline_outputs.get(ref)
            current = self._known_outputs.get(ref)
            series = output_series.get(ref, [])
            if not current and not series:
                continue

            sample_values = {
                (
                    sample["state"],
                    sample["raw_brightness"],
                    sample["effective_brightness"],
                )
                for sample in series
            }
            current_sample = current["sample"] if current else None
            baseline_sample = baseline["sample"] if baseline else None
            changed = (
                baseline_sample != current_sample
                or len(sample_values) > 1
                or (baseline_sample is None and bool(series))
            )
            if not changed:
                continue

            brightness_values = {
                sample["effective_brightness"]
                for sample in series
                if sample.get("state") is True
            }
            dimming_observed = len(brightness_values) > 1
            evidence = self._session["evidence"].setdefault(
                ref,
                {"hits": 0, "tap_hits": 0, "hold_hits": 0, "dimming_hits": 0},
            )
            evidence["hits"] += 1
            evidence[f"{run['action']}_hits"] += 1
            if dimming_observed:
                evidence["dimming_hits"] += 1

            output_meta = current or baseline or {}
            changed_outputs.append(
                {
                    "output_ref": ref,
                    "bus_id": output_meta.get("bus_id"),
                    "segment_id": output_meta.get("segment_id"),
                    "route_slug": output_meta.get("route_slug", ref.split(":")[0]),
                    "output_name": output_meta.get("output_name", ref.split(":")[1]),
                    "baseline": baseline_sample,
                    "current": current_sample,
                    "message_count": len(series),
                    "dimming_observed": dimming_observed,
                    "confidence": self._output_confidence(evidence, len(series), dimming_observed),
                }
            )

        changed_outputs.sort(
            key=lambda output: (
                -output["confidence"]["score"],
                output["route_slug"],
                output["output_name"],
            )
        )

        suggested_role = (
            "light"
            if any(output["dimming_observed"] for output in changed_outputs)
            else self._session["target_role"]
        )

        return {
            "action": run["action"],
            "phase": "complete",
            "captured_message_count": len(run["captured_messages"]),
            "changed_outputs": changed_outputs,
            "other_messages": [
                {
                    "arbitration_id": arbitration_id,
                    "count": count,
                    "sample_data": other_samples[arbitration_id],
                }
                for arbitration_id, count in other_messages.most_common(8)
            ],
            "confidence": self._session_confidence(changed_outputs),
            "suggested_role": suggested_role,
            "recommendations": self._recommendations(run["action"], changed_outputs),
        }

    def _output_confidence(
        self, evidence: Dict[str, int], message_count: int, dimming_observed: bool
    ) -> Dict[str, Any]:
        score = 45
        if message_count >= 2:
            score += 15
        if evidence["hits"] >= 2:
            score += 20
        if dimming_observed:
            score += 15
        level = "high" if score >= 80 else "medium" if score >= 60 else "low"
        return {"level": level, "score": min(score, 100)}

    def _session_confidence(self, changed_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not changed_outputs:
            return {
                "level": "low",
                "score": 20,
                "reasons": ["No authoritative Bloc9 output change was observed during the run."],
            }

        repeated = any(
            self._session["evidence"][output["output_ref"]]["hits"] >= 2
            for output in changed_outputs
        )
        if repeated:
            return {
                "level": "high",
                "score": 90,
                "reasons": [
                    "The same output changed in more than one guided run.",
                ],
            }

        return {
            "level": "medium",
            "score": 70,
            "reasons": ["At least one authoritative Bloc9 output changed during the run."],
        }

    def _recommendations(
        self, action: str, changed_outputs: List[Dict[str, Any]]
    ) -> List[str]:
        if not changed_outputs:
            return [
                "Repeat the countdown and interaction; no conclusive Bloc9 output change was captured.",
            ]

        recommendations = []
        if action == "tap":
            recommendations.append(
                "Run the press-and-hold capture next to confirm whether the light is dimmable."
            )
        if not any(output["confidence"]["level"] == "high" for output in changed_outputs):
            recommendations.append(
                "Repeat this capture once more to raise confidence before applying the mapping."
            )
        return recommendations

    def _phase_for_run(self, run: Dict[str, Any]) -> str:
        now = time.time()
        if now < run["press_at"]:
            return "countdown"
        if run["action"] == "hold" and now < run["release_at"]:
            return "holding"
        if now < run["capture_end_at"]:
            return "release" if run["action"] == "hold" else "capture"
        return "analysis"

    def _instruction_for_run(self, run: Dict[str, Any]) -> str:
        phase = self._phase_for_run(run)
        if phase == "countdown":
            return "Get ready. Follow the countdown and press the button at NOW."
        if phase == "holding":
            return "Press and hold the button now. Release when the next countdown finishes."
        if phase == "release":
            return "Release the button now while the helper watches the follow-up traffic."
        if phase == "capture":
            return "Press and release the button now."
        return "Analyzing captured traffic."

    def _countdown_for_run(self, run: Dict[str, Any]) -> Optional[int]:
        phase = self._phase_for_run(run)
        if phase == "countdown":
            return max(0, int(math.ceil(run["press_at"] - time.time())))
        if phase == "holding":
            return max(0, int(math.ceil(run["release_at"] - time.time())))
        return None

    def _output_ref(self, bus_id: int, segment_id: int, output_name: str) -> str:
        return f"{self._route_slug(bus_id, segment_id)}:{output_name}"

    def _output_ref_from_slug(self, route_slug: str, output_name: str) -> str:
        return f"{route_slug}:{output_name}"

    def _route_slug(self, bus_id: int, segment_id: int) -> str:
        return f"{bus_id}" if segment_id == 0 else f"{bus_id}_{segment_id}"

    def _empty_snapshot(self) -> Dict[str, Any]:
        return {
            "status": "idle",
            "target_name": "",
            "entity_id": None,
            "target_role": "light",
            "created_at": None,
            "known_output_count": len(self._known_outputs),
            "phase": "idle",
            "instruction": "Start a setup helper session to begin guided discovery.",
            "active_run": None,
            "completed_run": None,
        }
