#!/usr/bin/env python3
"""
Migration: Convert state file keys from s1-s6 format to entity_id format.

This migration was introduced in v6.2.9 when the state storage format changed
from using output identifiers (s1-s6) to using entity_ids (e.g., 'courtesy_lights').

The migration:
1. Loads the existing state file
2. Loads the scheiber configuration to get entity_id mappings
3. Converts state keys from 'sN' to entity_id format
4. Creates a backup of the old state file
5. Writes the new format

This maintains backward compatibility while migrating to the new format.
"""

import json
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime


def load_yaml_config(config_path):
    """Load YAML configuration file."""
    try:
        import yaml

        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to load config from {config_path}: {e}", file=sys.stderr)
        return None


def build_entity_id_mapping(config):
    """
    Build mapping from (device_id, output_name) to entity_id.

    Returns:
        dict: {(device_id, 's1'): 'entity_id', ...}
    """
    mapping = {}

    devices = config.get("devices", [])
    for device in devices:
        device_type = device.get("type")
        # Support both 'bus_id' (new) and 'id' (legacy)
        device_id = device.get("bus_id") or device.get("id")

        if device_type != "bloc9" or device_id is None:
            continue

        # Process lights
        lights = device.get("lights", {})
        for output_name, light_config in lights.items():
            name = light_config.get("name", output_name)
            entity_id = light_config.get("entity_id", name.lower().replace(" ", "_"))
            mapping[(device_id, output_name)] = entity_id

        # Process switches
        switches = device.get("switches", {})
        for output_name, switch_config in switches.items():
            name = switch_config.get("name", output_name)
            entity_id = switch_config.get("entity_id", name.lower().replace(" ", "_"))
            mapping[(device_id, output_name)] = entity_id

    return mapping


def migrate_state_file(state_path, config_path, dry_run=False):
    """
    Migrate state file from old format to new format.

    Args:
        state_path: Path to state file
        config_path: Path to scheiber config file
        dry_run: If True, don't write changes

    Returns:
        bool: True if migration successful or not needed, False on error
    """
    print(f"Migration 001: Migrating state keys from s1-s6 to entity_id format")
    print(f"State file: {state_path}")
    print(f"Config file: {config_path}")

    # Check if state file exists
    if not os.path.exists(state_path):
        print(f"No state file found at {state_path}, skipping migration")
        return True

    # Check if config exists
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found at {config_path}")
        return False

    # Load state file
    try:
        with open(state_path, "r") as f:
            state_data = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load state file: {e}")
        return False

    # Load config
    config = load_yaml_config(config_path)
    if not config:
        return False

    # Build entity_id mapping
    mapping = build_entity_id_mapping(config)
    print(f"Found {len(mapping)} entity_id mappings")

    # Check if migration needed
    needs_migration = False
    for device_key, device_state in state_data.items():
        # device_key format: "bloc9_1", "bloc9_2", etc.
        if not device_key.startswith("bloc9_"):
            continue

        device_id = int(device_key.split("_")[1])

        # Check if any keys use old format (s1-s6)
        for output_key in device_state.keys():
            if output_key.startswith("s") and output_key[1:].isdigit():
                needs_migration = True
                break

        if needs_migration:
            break

    if not needs_migration:
        print("State file already uses entity_id format, no migration needed")
        return True

    print("Migrating state file...")

    # Migrate state data
    new_state_data = {}
    migration_count = 0

    for device_key, device_state in state_data.items():
        if not device_key.startswith("bloc9_"):
            # Keep non-bloc9 devices as-is
            new_state_data[device_key] = device_state
            continue

        device_id = int(device_key.split("_")[1])
        new_device_state = {}

        for output_key, output_state in device_state.items():
            # Check if this is old format (s1-s6)
            if output_key.startswith("s") and output_key[1:].isdigit():
                # Look up entity_id
                entity_id = mapping.get((device_id, output_key))
                if entity_id:
                    new_device_state[entity_id] = output_state
                    migration_count += 1
                    print(f"  {device_key}/{output_key} -> {entity_id}")
                else:
                    # No mapping found, keep old key
                    print(
                        f"  WARNING: No mapping found for {device_key}/{output_key}, keeping old key"
                    )
                    new_device_state[output_key] = output_state
            else:
                # Already in new format or unknown format
                new_device_state[output_key] = output_state

        new_state_data[device_key] = new_device_state

    print(f"Migrated {migration_count} state entries")

    if dry_run:
        print("DRY RUN: Would write migrated state file")
        return True

    # Create backup
    backup_path = f"{state_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        with open(backup_path, "w") as f:
            json.dump(state_data, f, indent=2)
        print(f"Created backup: {backup_path}")
    except Exception as e:
        print(f"ERROR: Failed to create backup: {e}")
        return False

    # Write new state file
    try:
        with open(state_path, "w") as f:
            json.dump(new_state_data, f, indent=2)
        print(f"Successfully wrote migrated state file")
        return True
    except Exception as e:
        print(f"ERROR: Failed to write state file: {e}")
        # Try to restore backup
        try:
            with open(backup_path, "r") as f:
                backup_data = json.load(f)
            with open(state_path, "w") as f:
                json.dump(backup_data, f, indent=2)
            print("Restored backup after write failure")
        except:
            pass
        return False


def main():
    parser = argparse.ArgumentParser(description="Migrate state file format")
    parser.add_argument("--data-dir", required=True, help="Data directory path")
    parser.add_argument("--config-file", required=True, help="Config file path")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no changes)")

    args = parser.parse_args()

    # Construct paths
    state_path = os.path.join(args.data_dir, "scheiber_state.json")
    config_path = args.config_file

    # Run migration
    success = migrate_state_file(state_path, config_path, args.dry_run)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
