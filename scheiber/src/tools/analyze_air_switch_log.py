#!/usr/bin/env python3
"""Analyze a Scheiber Air Switch interactions log for pattern evidence.

Reads the JSON Lines log written by the setup web UI's Interactions tab
(``<data_dir>/interactions_log.jsonl`` by default) and prints, per saved
capture session:

- which (identity, button_index) pairs were confirmed for each guided
  function (top/bottom, or top-left/bottom-left/top-right/bottom-right),
  and whether more than one pair showed up for a single function (a sign of
  a misfire, a second nearby unit, or more than one wireless receiver
  reporting the same press independently);
- Bloc9/panel reactions recorded for each function, to help confirm which
  physical output(s) a function actually controls;
- unconfirmed companion frames (e.g. 0x0402xxxx/0x0408xxxx) seen alongside
  button presses, grouped by arbitration ID, as a starting point for
  investigating how multiple wireless receivers might avoid duplicate
  reports.

It also prints a cross-session summary grouping every observed identity
across all saved sessions, to help notice whether the same identity was
captured at more than one location (suggesting a single unit was tested
twice) or whether different physical units unexpectedly share an identity.

Usage:
    python3 analyze_air_switch_log.py [path/to/interactions_log.jsonl]

If no path is given, defaults to ``/data/interactions_log.jsonl`` (the
add-on's default data directory).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


def load_sessions(path: Path) -> List[Dict[str, Any]]:
    sessions = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                sessions.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"Skipping malformed line {line_number}: {exc}", file=sys.stderr)
    return sessions


def format_timestamp(epoch: float | None) -> str:
    if not epoch:
        return "unknown time"
    import datetime

    return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def summarize_step_identities(step: Dict[str, Any]) -> Counter:
    """Count (identity, button_index) pairs confirmed within one step."""
    counts: Counter = Counter()
    for event in step.get("events", []):
        confirmed = event.get("confirmed_air_switch")
        if confirmed:
            counts[(confirmed["identity_hex"], confirmed["button_index"])] += 1
    return counts


def print_session(session: Dict[str, Any]) -> None:
    print("=" * 72)
    print(
        f"Location: {session.get('location')!r}  "
        f"Unit type: {session.get('button_count')}-function  "
        f"Saved: {format_timestamp(session.get('saved_at'))}"
    )
    print("=" * 72)

    for step in session.get("steps", []):
        identity_counts = summarize_step_identities(step)
        reactions = step.get("reactions", [])
        companions = step.get("companion_frames", [])

        print(f"\n  Function: {step.get('label')}")
        print(f"    Button-source frames captured: {len(step.get('events', []))}")

        if identity_counts:
            for (identity, button_index), count in identity_counts.most_common():
                print(
                    f"    -> identity={identity} button_index={button_index} ({count}x)"
                )
            if len(identity_counts) > 1:
                print(
                    "    ! Multiple distinct identity/button_index pairs seen for "
                    "this single function - check for a misfire, a second nearby "
                    "unit, or more than one receiver reporting independently."
                )
        else:
            print("    -> no confirmed wireless Air Switch identity decoded")

        if reactions:
            route_counts: Counter = Counter(
                (reaction.get("route_slug"), tuple(sorted(reaction.get("outputs", {}))))
                for reaction in reactions
            )
            for (route_slug, output_names), count in route_counts.most_common():
                print(
                    f"    Reaction: Bloc9 #{route_slug} outputs "
                    f"{', '.join(output_names)} ({count}x)"
                )
        else:
            print("    Reaction: none recorded")

        if companions:
            companion_ids = Counter(entry["arbitration_id"] for entry in companions)
            ids_summary = ", ".join(
                f"{arb_id} ({count}x)" for arb_id, count in companion_ids.most_common()
            )
            print(f"    Companion frames: {ids_summary}")


def print_cross_session_identity_summary(sessions: Iterable[Dict[str, Any]]) -> None:
    identity_locations: Dict[str, set] = defaultdict(set)
    identity_functions: Dict[str, Counter] = defaultdict(Counter)

    for session in sessions:
        location = session.get("location") or "unknown"
        for step in session.get("steps", []):
            for event in step.get("events", []):
                confirmed = event.get("confirmed_air_switch")
                if not confirmed:
                    continue
                identity = confirmed["identity_hex"]
                identity_locations[identity].add(location)
                identity_functions[identity][
                    (step.get("label"), confirmed["button_index"])
                ] += 1

    if not identity_locations:
        return

    print("\n" + "#" * 72)
    print("# Cross-session identity summary")
    print("#" * 72)
    for identity, locations in sorted(identity_locations.items()):
        print(f"\nIdentity {identity}:")
        print(f"  Seen at locations: {', '.join(sorted(locations))}")
        if len(locations) > 1:
            print(
                "  ! Same identity captured at more than one location - either "
                "the same physical unit was tested more than once, or this "
                "identity is not as unique as expected."
            )
        for (label, button_index), count in identity_functions[identity].most_common():
            print(f"    function={label!r} button_index={button_index} ({count}x)")


def main(argv: List[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("/data/interactions_log.jsonl")
    if not path.exists():
        print(f"No interactions log found at {path}", file=sys.stderr)
        return 1

    sessions = load_sessions(path)
    if not sessions:
        print(f"No saved sessions found in {path}")
        return 0

    print(f"Loaded {len(sessions)} saved session(s) from {path}\n")
    for session in sessions:
        print_session(session)

    print_cross_session_identity_summary(sessions)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
