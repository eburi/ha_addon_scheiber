#!/usr/bin/env python3
"""
Compare two MQTT snapshots to find differences between versions.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Set


def load_snapshot(filepath: str) -> Dict[str, Any]:
    """Load a snapshot JSON file."""
    with open(filepath) as f:
        return json.load(f)


def compare_entity_configs(
    entity_id: str, v1_config: str, v2_config: str
) -> Dict[str, Any]:
    """Compare config payloads for a single entity."""
    differences = {}

    try:
        c1 = json.loads(v1_config)
        c2 = json.loads(v2_config)

        # Find keys only in one version
        keys1 = set(c1.keys())
        keys2 = set(c2.keys())

        only_in_v1 = keys1 - keys2
        only_in_v2 = keys2 - keys1
        common_keys = keys1 & keys2

        if only_in_v1:
            differences["only_in_v1"] = {k: c1[k] for k in only_in_v1}
        if only_in_v2:
            differences["only_in_v2"] = {k: c2[k] for k in only_in_v2}

        # Compare common keys
        changed = {}
        for key in common_keys:
            if c1[key] != c2[key]:
                changed[key] = {"v1": c1[key], "v2": c2[key]}

        if changed:
            differences["changed"] = changed

    except json.JSONDecodeError:
        differences["error"] = "Could not parse JSON"

    return differences


def compare_snapshots(snapshot1_path: str, snapshot2_path: str):
    """Compare two MQTT snapshots and report differences."""
    s1 = load_snapshot(snapshot1_path)
    s2 = load_snapshot(snapshot2_path)

    v1_name = Path(snapshot1_path).stem
    v2_name = Path(snapshot2_path).stem

    print("=" * 80)
    print(f"MQTT SNAPSHOT COMPARISON: {v1_name} vs {v2_name}")
    print("=" * 80)
    print()

    # Metadata comparison
    print("Metadata:")
    print(
        f"  {v1_name}: {s1['metadata']['total_topics']} topics captured at {s1['metadata']['capture_time']}"
    )
    print(
        f"  {v2_name}: {s2['metadata']['total_topics']} topics captured at {s2['metadata']['capture_time']}"
    )
    print()

    # Compare lights
    print("=" * 80)
    print("LIGHTS")
    print("=" * 80)

    lights1 = set(s1.get("lights", {}).keys())
    lights2 = set(s2.get("lights", {}).keys())

    only_in_v1 = lights1 - lights2
    only_in_v2 = lights2 - lights1
    common_lights = lights1 & lights2

    if only_in_v1:
        print(f"\n❌ Only in {v1_name}: {len(only_in_v1)} lights")
        for light in sorted(only_in_v1):
            print(f"   - {light}")

    if only_in_v2:
        print(f"\n✅ Only in {v2_name}: {len(only_in_v2)} lights")
        for light in sorted(only_in_v2):
            print(f"   - {light}")

    if not only_in_v1 and not only_in_v2:
        print(f"✅ Same lights in both versions: {len(common_lights)}")

    # Compare light configs
    config_differences = {}
    for light_id in common_lights:
        v1_topics = s1["lights"][light_id]
        v2_topics = s2["lights"][light_id]

        if "config" in v1_topics and "config" in v2_topics:
            diffs = compare_entity_configs(
                light_id, v1_topics["config"], v2_topics["config"]
            )
            if diffs:
                config_differences[light_id] = diffs

    if config_differences:
        print(f"\n⚠️  Config differences found in {len(config_differences)} lights:")
        for light_id, diffs in sorted(config_differences.items()):
            print(f"\n  🔍 {light_id}:")
            if "only_in_v1" in diffs:
                print(f"     Only in {v1_name}:")
                for k, v in diffs["only_in_v1"].items():
                    print(f"       - {k}: {v}")
            if "only_in_v2" in diffs:
                print(f"     Only in {v2_name}:")
                for k, v in diffs["only_in_v2"].items():
                    print(f"       - {k}: {v}")
            if "changed" in diffs:
                print(f"     Changed values:")
                for k, vals in diffs["changed"].items():
                    print(f"       - {k}:")
                    print(f"           {v1_name}: {vals['v1']}")
                    print(f"           {v2_name}: {vals['v2']}")
    else:
        print(f"✅ All light configs are identical")

    # Compare switches
    print()
    print("=" * 80)
    print("SWITCHES")
    print("=" * 80)

    switches1 = set(s1.get("switches", {}).keys())
    switches2 = set(s2.get("switches", {}).keys())

    only_in_v1_sw = switches1 - switches2
    only_in_v2_sw = switches2 - switches1
    common_switches = switches1 & switches2

    if only_in_v1_sw:
        print(f"\n❌ Only in {v1_name}: {len(only_in_v1_sw)} switches")
        for switch in sorted(only_in_v1_sw):
            print(f"   - {switch}")

    if only_in_v2_sw:
        print(f"\n✅ Only in {v2_name}: {len(only_in_v2_sw)} switches")
        for switch in sorted(only_in_v2_sw):
            print(f"   - {switch}")

    if not only_in_v1_sw and not only_in_v2_sw:
        print(f"✅ Same switches in both versions: {len(common_switches)}")

    # Compare switch configs
    switch_config_differences = {}
    for switch_id in common_switches:
        v1_topics = s1["switches"][switch_id]
        v2_topics = s2["switches"][switch_id]

        if "config" in v1_topics and "config" in v2_topics:
            diffs = compare_entity_configs(
                switch_id, v1_topics["config"], v2_topics["config"]
            )
            if diffs:
                switch_config_differences[switch_id] = diffs

    if switch_config_differences:
        print(
            f"\n⚠️  Config differences found in {len(switch_config_differences)} switches:"
        )
        for switch_id, diffs in sorted(switch_config_differences.items()):
            print(f"\n  🔍 {switch_id}:")
            if "only_in_v1" in diffs:
                print(f"     Only in {v1_name}:")
                for k, v in diffs["only_in_v1"].items():
                    print(f"       - {k}: {v}")
            if "only_in_v2" in diffs:
                print(f"     Only in {v2_name}:")
                for k, v in diffs["only_in_v2"].items():
                    print(f"       - {k}: {v}")
            if "changed" in diffs:
                print(f"     Changed values:")
                for k, vals in diffs["changed"].items():
                    print(f"       - {k}:")
                    print(f"           {v1_name}: {vals['v1']}")
                    print(f"           {v2_name}: {vals['v2']}")
    else:
        print(f"✅ All switch configs are identical")

    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total_issues = (
        len(only_in_v1)
        + len(only_in_v2)
        + len(only_in_v1_sw)
        + len(only_in_v2_sw)
        + len(config_differences)
        + len(switch_config_differences)
    )

    if total_issues == 0:
        print("🎉 No differences found - versions are identical!")
    else:
        print(f"⚠️  Found {total_issues} differences:")
        if only_in_v1:
            print(f"   - {len(only_in_v1)} lights only in {v1_name}")
        if only_in_v2:
            print(f"   - {len(only_in_v2)} lights only in {v2_name}")
        if only_in_v1_sw:
            print(f"   - {len(only_in_v1_sw)} switches only in {v1_name}")
        if only_in_v2_sw:
            print(f"   - {len(only_in_v2_sw)} switches only in {v2_name}")
        if config_differences:
            print(f"   - {len(config_differences)} lights with config differences")
        if switch_config_differences:
            print(
                f"   - {len(switch_config_differences)} switches with config differences"
            )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python compare_mqtt_snapshots.py <snapshot1.json> <snapshot2.json>"
        )
        print("\nExample:")
        print(
            "  python compare_mqtt_snapshots.py mqtt_snapshot_v5.json mqtt_snapshot_v6.json"
        )
        sys.exit(1)

    snapshot1 = sys.argv[1]
    snapshot2 = sys.argv[2]

    if not Path(snapshot1).exists():
        print(f"Error: {snapshot1} not found")
        sys.exit(1)

    if not Path(snapshot2).exists():
        print(f"Error: {snapshot2} not found")
        sys.exit(1)

    compare_snapshots(snapshot1, snapshot2)
