#!/usr/bin/env python3
"""Test config_loader integrity checks and entity_id generation."""

import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "scheiber" / "src"))

from config_loader import load_config, generate_entity_id_from_name


def test_entity_id_generation():
    """Test entity_id generation from name."""
    print("\n=== Testing entity_id generation ===")

    test_cases = [
        ("Salon Working Light", "light", "light.salon_working_light"),
        ("12V Electronics", "switch", "switch.12v_electronics"),
        ("Water Pump #1", "switch", "switch.water_pump_1"),
        ("Main/Salon Light", "light", "light.mainsalon_light"),
        ("Test___Multiple___Spaces", "light", "light.test_multiple_spaces"),
        ("  Leading and Trailing  ", "switch", "switch.leading_and_trailing"),
    ]

    for name, component, expected in test_cases:
        result = generate_entity_id_from_name(name, component)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{name}' -> '{result}' (expected: '{expected}')")


def test_config_with_optional_entity_id():
    """Test config loading with optional entity_id."""
    print("\n=== Testing optional entity_id ===")

    config_yaml = """
bloc9:
  - bus_id: 7
    name: "Test Bloc9"
    lights:
      - name: "Salon Working Light"
        output: s1
      - name: "Reading Light"
        entity_id: "light.custom_reading_light"
        output: s2
    switches:
      - name: "Water Pump"
        output: s3
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_path = f.name

    try:
        config = load_config(config_path)
        if config:
            print(f"✓ Config loaded successfully: {config.get_summary()}")
            configs = config.get_bloc9_configs(7)
            for cfg in configs:
                print(
                    f"  - {cfg.component}.{cfg.entity_id} (output: {cfg.output}, name: {cfg.name})"
                )
        else:
            print("✗ Failed to load config")
    finally:
        Path(config_path).unlink()


def test_duplicate_output_detection():
    """Test detection of duplicate output assignments."""
    print("\n=== Testing duplicate output detection ===")

    config_yaml = """
bloc9:
  - bus_id: 7
    name: "Test Bloc9"
    lights:
      - name: "Light 1"
        output: s1
      - name: "Light 2"
        output: s1
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_path = f.name

    try:
        config = load_config(config_path)
        print("✗ Should have raised ValueError for duplicate output")
    except ValueError as e:
        if "assigned to multiple entities" in str(e):
            print(f"✓ Correctly detected duplicate output: {e}")
        else:
            print(f"✗ Wrong error: {e}")
    finally:
        Path(config_path).unlink()


def test_duplicate_entity_id_detection():
    """Test detection of duplicate entity_id."""
    print("\n=== Testing duplicate entity_id detection ===")

    config_yaml = """
bloc9:
  - bus_id: 7
    name: "Test Bloc9"
    lights:
      - name: "Light 1"
        entity_id: "light.my_light"
        output: s1
  - bus_id: 8
    name: "Test Bloc9 2"
    lights:
      - name: "Light 2"
        entity_id: "light.my_light"
        output: s1
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_path = f.name

    try:
        config = load_config(config_path)
        print("✗ Should have raised ValueError for duplicate entity_id")
    except ValueError as e:
        if "used multiple times" in str(e):
            print(f"✓ Correctly detected duplicate entity_id: {e}")
        else:
            print(f"✗ Wrong error: {e}")
    finally:
        Path(config_path).unlink()


def test_auto_generated_entity_id_collision():
    """Test detection of collision when auto-generated entity_id matches existing one."""
    print("\n=== Testing auto-generated entity_id collision ===")

    config_yaml = """
bloc9:
  - bus_id: 7
    name: "Test Bloc9"
    lights:
      - name: "Salon Light"
        entity_id: "light.salon_light"
        output: s1
      - name: "Salon Light"
        output: s2
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(config_yaml)
        config_path = f.name

    try:
        config = load_config(config_path)
        print("✗ Should have raised ValueError for duplicate entity_id")
    except ValueError as e:
        if "used multiple times" in str(e):
            print(f"✓ Correctly detected collision: {e}")
        else:
            print(f"✗ Wrong error: {e}")
    finally:
        Path(config_path).unlink()


if __name__ == "__main__":
    test_entity_id_generation()
    test_config_with_optional_entity_id()
    test_duplicate_output_detection()
    test_duplicate_entity_id_detection()
    test_auto_generated_entity_id_collision()

    print("\n=== All tests completed ===")
