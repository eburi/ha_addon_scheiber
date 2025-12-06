# GitHub Copilot / AI Agent Instructions — scheiber

This file contains targeted, actionable guidance for an AI coding agent working in this repository.
Keep updates short and concrete; prefer small, focused edits using the repo's existing conventions.

Core purpose
- This repository provides Python utilities that interact with scheiber devices over a SocketCAN bus.
- Key runtime integration points: `python-can` (socketcan backend), core modules in `scheiber/src/`, and debugging tools in `scheiber/src/tools/`.

**Working directory assumption**
- Production code in `scheiber/src/` runs with `scheiber/src/` as the working directory.
- Debug tools in `scheiber/src/tools/` add parent directory to path: `sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))`
- Data files for debug tools are in `scheiber/src/tools/data/`.
- When testing locally, run scripts from the src folder or adjust sys.path accordingly.

Important files and their roles
- **Production code (scheiber/src/)**:
  - `can_decoder.py`: CAN message decoding utilities (find_device_and_matcher, extract_property_value)
  - `device_types.yaml`: YAML configuration defining device types, matchers, and property extraction templates
  - `mqtt_bridge.py`: Main MQTT bridge program that publishes CAN messages to MQTT broker
  - `devices.py`: Device class hierarchy with ScheiberCanDevice base and Bloc9 concrete class
  - `scheiber.py`: Low-level CAN command functions (bloc9_switch, send_burst)
  - `requirements.txt`: Python dependencies (python-can, paho-mqtt, PyYAML)

- **Debug/analysis tools (scheiber/src/tools/)**:
  - `canlistener.py`: CAN listener for debugging (shows decoded messages)
  - `analyser.py`: Interactive CAN sniffer (press spacebar to clear screen)
  - `analyze_dimming.py`: Analysis tool to identify dimming byte patterns
  - `light.py`: push_light_button() helper (sends two-packet press/release sequence)
  - `data/`: Sample CAN dumps for protocol analysis
    - `command.md`: Verified command protocol for S5/S6 switches showing 0-indexed switch numbers
  - `can_names.csv`: Human-readable mapping of known arbitration IDs

- **Deployment (scheiber/)**:
  - `config.yaml`: Home Assistant addon configuration with version, options, and schema
  - `Dockerfile`: Container build configuration with virtualenv setup in /src
  - `run.sh`: Deployment script that activates virtualenv and starts mqtt_bridge.py

Key patterns and protocols (must be respected)
- Bloc9 CAN-ID construction (used when sending commands):
  - Build a byte by: `(bloc9_id << 3) | 0x80` (set MSB and shift left 3)
  - OR that byte into the low byte of `0x02360600` to make the full arbitration id.
    Example: `bloc9_id = 10` -> lowest byte = `0xD0`, full id `0x023606D0`.
- Command payload for switching: 4 bytes
  - Byte 0: `switch_nr` (numeric)
  - Byte 1: `0x01` for ON or `0x00` for OFF
  - Bytes 2..3: `0x00, 0x00`
- Known status prefixes (upper 24 bits):
  - `0x00000600` — Bloc9 low-priority status
  - `0x02160600` — S1 & S2 change messages
  - `0x02180600` — S3 & S4 change messages
  - `0x021A0600` — S5 & S6 change messages

Agent coding rules for this repo
- Follow existing style (snake_case functions, concise helpers in `scheiber/src`).
- When changing code that opens `can.interface.Bus`, always open in a try/finally and call `bus.shutdown()` in `finally`.
- Use `apply_patch` for edits (small focused patches). Don't reformat whole files.
- Avoid touching hardware-specific code unless the change is clearly safer (e.g., better error handling or clear abstractions). When in doubt, add a small wrapper or feature-flag.
- **Version management**: After making any code changes, update the `version` field in `scheiber/config.yaml` following semantic versioning (semver):
  - **PATCH** (0.0.X): Bug fixes, small tweaks, no API changes
  - **MINOR** (0.X.0): New features, backward-compatible changes (new parameters with defaults, new optional functionality)
  - **MAJOR** (X.0.0): Breaking changes (API changes, removed functionality, changed behavior)
  - Example: `0.5.8` → `0.5.9` for bug fix, `0.5.8` → `0.6.0` for new feature, `0.5.8` → `1.0.0` for breaking change

Common developer workflows (how to run things locally)
- Install runtime deps (if not present): `pip install python-can paho-mqtt PyYAML`
- Python environment: virtualenv at `scheiber/src/.venv` with dependencies from `requirements.txt`
- **All scripts run from the `scheiber/src/` folder:**
  - Test switch sequence: `cd scheiber/src && python scheiber.py 3 7`
  - MQTT bridge: `cd scheiber/src && python mqtt_bridge.py --debug --mqtt-host localhost --mqtt-port 1883`
- **Debug tools run from `scheiber/src/tools/`:**
  - CAN listener: `cd scheiber/src/tools && python canlistener.py can1`
  - Interactive analyzer: `cd scheiber/src/tools && python analyser.py -i can0` (spacebar to clear)
  - Light button: `cd scheiber/src/tools && python light.py can1`
  - Dimming analysis: `cd scheiber/src/tools && python analyze_dimming.py can1`

What agents should do first (on a new task)
1. Read `scheiber/src/tools/can_names.csv` and `scheiber/src/tools/data/` to understand message examples.
2. Prefer changes in `scheiber/src/*` for production code.
3. When adding decoding rules, update `scheiber/src/device_types.yaml` with new device types, matchers, or properties.

Development environment
- Python virtualenv: `scheiber/src/.venv` (created by Dockerfile, used by run.sh)
- VS Code settings: `.vscode/settings.json` points to virtualenv interpreter
- Code formatting: Black formatter with format-on-save enabled
- Dependencies: `python-can==4.3.1`, `paho-mqtt==2.1.0`, `PyYAML==6.0.1` (see `scheiber/src/requirements.txt`)

MQTT topic conventions
- **IMPORTANT**: The mqtt_bridge.py uses a configurable `--mqtt-topic-prefix` (default: "homeassistant")
- All MQTT topics use this prefix variable, NOT hardcoded strings
- The prefix provides the top-level MQTT namespace. "homeassistant" is the default because:
  - Home Assistant MQTT Discovery automatically looks under `/homeassistant` for discovery configs
  - Topics then become `homeassistant/scheiber/<device_type>/<bus_id>/<property>/config`
  - This avoids needing to configure discovery_prefix in Home Assistant
- If a different prefix is used (e.g., "boat"), topics would be `boat/scheiber/<device_type>/<bus_id>/<property>/config`
- Topic structure (where `<prefix>` = mqtt_topic_prefix):
  - Discovery configs: `<prefix>/scheiber/<device_type>/<bus_id>/<property>/config`
  - State topics: `<prefix>/scheiber/<device_type>/<bus_id>/<property>/state`
  - Command topics: `<prefix>/scheiber/<device_type>/<bus_id>/<property>/set`
  - Brightness state: `<prefix>/scheiber/<device_type>/<bus_id>/<property>/brightness`
  - Brightness command: `<prefix>/scheiber/<device_type>/<bus_id>/<property>/set_brightness`
- **NEVER hardcode "homeassistant" in topic patterns** - always use the configurable prefix variable
- The `/scheiber/` namespace after the prefix keeps scheiber-related topics organized and separated


Testing and safety
- There are no automated tests. Add small runnable scripts that can be executed without hardware by mocking `can.interface.Bus` or by guarding with `if __name__ == '__main__'`.
- Keep hardware-side changes minimal. Prefer adding a `dry_run` boolean parameter to functions that would otherwise send onto a real CAN bus.

If you need clarification
- Ask for a small concrete artifact (e.g., a single representative dump line) before changing decoding heuristics.

End of instructions — request feedback if anything here is unclear.
