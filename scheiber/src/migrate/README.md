# Migration Scripts

This directory contains migration scripts that run automatically when the addon starts.

## How It Works

1. When `run.sh` starts, it checks for the `migrate/` directory
2. It maintains a tracker file at `${DATA_DIR}/.migrations_applied`
3. Each migration script is run once (tracked by filename)
4. Migrations are run in alphabetical order (use numeric prefixes: 001_, 002_, etc.)
5. If a migration fails, the startup process stops

## Migration Script Types

### Python Scripts (*.py)

- Run with Python interpreter
- Virtual environment is already activated
- Receive arguments: `--data-dir ${DATA_DIR} --config-file ${CONFIG_FILE}`
- Must exit with code 0 on success, non-zero on failure
- Example:
  ```python
  #!/usr/bin/env python3
  import argparse
  import sys
  
  def main():
      parser = argparse.ArgumentParser()
      parser.add_argument('--data-dir', required=True)
      parser.add_argument('--config-file', required=True)
      args = parser.parse_args()
      
      # Do migration work
      print("Running migration...")
      
      sys.exit(0)  # Success
  
  if __name__ == '__main__':
      main()
  ```

### Shell Scripts (*.sh)

- Run with bash interpreter
- Receive positional arguments: `$1` = DATA_DIR, `$2` = CONFIG_FILE
- Must exit with code 0 on success, non-zero on failure
- Example:
  ```bash
  #!/bin/bash
  DATA_DIR="$1"
  CONFIG_FILE="$2"
  
  echo "Running migration..."
  
  # Do migration work
  
  exit 0  # Success
  ```

## Naming Convention

Use numeric prefixes for ordering:
- `001_initial_migration.py`
- `002_add_new_feature.sh`
- `003_update_config_format.py`

## Current Migrations

### 001_migrate_state_keys_to_entity_id.py

**Version:** 6.2.9+  
**Purpose:** Convert state file keys from `s1-s6` format to `entity_id` format

This migration handles the breaking change introduced in v6.2.9 where state storage
changed from using output identifiers (s1-s6) to using entity_ids.

**What it does:**
1. Loads existing state file (`scheiber_state.json`)
2. Loads configuration to get entity_id mappings
3. Converts state keys: `"s1"` → `"courtesy_lights"`, etc.
4. Creates backup with timestamp
5. Writes migrated state file

**Example:**
```json
// Before
{
  "bloc9_10": {
    "s1": {"brightness": 205, "state": true},
    "s2": {"brightness": 0, "state": false}
  }
}

// After
{
  "bloc9_10": {
    "courtesy_lights": {"brightness": 205, "state": true},
    "secret_light": {"brightness": 0, "state": false}
  }
}
```

**Safety:**
- Creates timestamped backup before making changes
- Only migrates keys that match old format
- Preserves keys already in new format
- Can be run multiple times safely (idempotent)

## Testing Migrations

Test locally before deploying:

```bash
# Python migration
python3 migrate/001_migrate_state_keys_to_entity_id.py \
  --data-dir /data \
  --config-file /config/scheiber-config.yaml \
  --dry-run

# Shell migration (with dry-run logic in script)
bash migrate/002_example.sh /data /config/scheiber-config.yaml
```

## Best Practices

1. **Make migrations idempotent** - Safe to run multiple times
2. **Create backups** - Always backup before modifying files
3. **Validate inputs** - Check file existence and format
4. **Log clearly** - Print what's happening for debugging
5. **Handle errors** - Exit with non-zero code on failure
6. **Test thoroughly** - Test on sample data before deployment
7. **Document changes** - Update this README when adding migrations
