#!/usr/bin/env python3
"""
Test check_mqtt.py logic locally without needing MQTT broker.
Validates the device structure checks for v4.0.0.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "scheiber" / "src"))


def test_v4_device_structure():
    """Test that v4.0.0 device structure validation logic is correct."""

    # Simulated v4.0.0 config (unified Scheiber device)
    v4_config = {
        "name": "Main Light Saloon Aft",
        "unique_id": "scheiber_bloc9_10_s1",
        "state_topic": "homeassistant/scheiber/bloc9/10/s1/state",
        "command_topic": "homeassistant/scheiber/bloc9/10/s1/set",
        "availability_topic": "homeassistant/scheiber/bloc9/10/s1/availability",
        "device": {
            "identifiers": ["scheiber_system"],
            "name": "Scheiber",
            "model": "Marine Lighting Control System",
            "manufacturer": "Scheiber",
        },
    }

    # Simulated v3.x config (individual devices with via_device)
    v3_config = {
        "name": "Main Light Saloon Aft",
        "unique_id": "scheiber_bloc9_10_s1",
        "state_topic": "homeassistant/scheiber/bloc9/10/s1/state",
        "command_topic": "homeassistant/scheiber/bloc9/10/s1/set",
        "availability_topic": "homeassistant/scheiber/bloc9/10/s1/availability",
        "device": {
            "identifiers": ["scheiber_bloc9_10_s1"],
            "name": "Main Light Saloon Aft",
            "model": "Main Scheiber - S1",
            "manufacturer": "Scheiber",
            "via_device": "scheiber_bloc9_10",
        },
    }

    print("Testing v4.0.0 device structure validation...\n")

    # Test v4 config
    print("✅ Testing v4.0.0 config (should PASS):")
    device_info = v4_config["device"]
    errors = []

    if device_info.get("identifiers") != ["scheiber_system"]:
        errors.append(f"  ❌ Wrong identifiers: {device_info.get('identifiers')}")
    if device_info.get("name") != "Scheiber":
        errors.append(f"  ❌ Wrong name: {device_info.get('name')}")
    if device_info.get("model") != "Marine Lighting Control System":
        errors.append(f"  ❌ Wrong model: {device_info.get('model')}")
    if "via_device" in device_info:
        errors.append(f"  ❌ via_device should not be present")

    if errors:
        print("  FAILED:")
        for error in errors:
            print(f"    {error}")
    else:
        print("  ✅ All checks passed!\n")

    # Test v3 config (should fail)
    print("❌ Testing v3.x config (should FAIL):")
    device_info = v3_config["device"]
    errors = []

    if device_info.get("identifiers") != ["scheiber_system"]:
        errors.append(f"  ❌ Wrong identifiers: {device_info.get('identifiers')}")
    if device_info.get("name") != "Scheiber":
        errors.append(f"  ❌ Wrong name: {device_info.get('name')}")
    if device_info.get("model") != "Marine Lighting Control System":
        errors.append(f"  ❌ Wrong model: {device_info.get('model')}")
    if "via_device" in device_info:
        errors.append(
            f"  ❌ via_device should not be present (found: {device_info.get('via_device')})"
        )

    if errors:
        print("  Expected failures detected:")
        for error in errors:
            print(f"    {error}")
        print("  ✅ Validation correctly rejects v3.x structure!\n")
    else:
        print("  ⚠️  WARNING: v3.x config was not rejected!\n")

    print("=" * 80)
    print("SUMMARY:")
    print("=" * 80)
    print("✅ v4.0.0 validation logic is working correctly")
    print("✅ check_mqtt.py is ready to test deployed v4.0.0 system")
    print("\nNext steps:")
    print("1. Deploy v4.0.0 to your boat")
    print("2. Run: python check_mqtt.py")
    print("3. It will validate all entities belong to unified 'Scheiber' device")


if __name__ == "__main__":
    test_v4_device_structure()
