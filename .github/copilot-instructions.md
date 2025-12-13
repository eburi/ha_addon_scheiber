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
  - `scheiber_device.py`: **Hardware abstraction layer** - Device classes with CAN protocol implementation
    - `ScheiberCanDevice`: Base class with observer pattern (subscribe/unsubscribe/notify)
    - `Bloc9Device`: Bloc9 CAN protocol, brightness control, transitions, flash effects
    - `Bloc7Device`: Tank sensor stub (read-only)
    - `TransitionController`: Smooth brightness transitions with easing (50Hz, 20ms steps)
    - `FlashController`: Flash effects with state restoration
  - `devices.py`: **MQTT/Home Assistant bridge layer** - MQTT handlers for device types
    - `ScheiberCanDeviceMqttHandler`: Abstract base for MQTT bridges
    - `Bloc9`: MQTT handler that uses Bloc9Device, subscribes as observer, publishes to MQTT
    - Handles Home Assistant discovery, entity configuration, state persistence
  - `can_decoder.py`: CAN message decoding utilities (find_device_and_matcher, extract_property_value)
  - `device_types.yaml`: YAML configuration defining device types, matchers, and property extraction templates
  - `mqtt_bridge.py`: Main MQTT bridge program that publishes CAN messages to MQTT broker
  - `scheiber.py`: Low-level CAN command functions (bloc9_switch, send_burst) - **deprecated, use Bloc9Device instead**
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
  - `0x00000600` — Bloc9 low-priority status (heartbeat, DO NOT use for state updates)
  - `0x02160600` — S1 & S2 change messages (8 bytes, actual state updates)
  - `0x02180600` — S3 & S4 change messages (8 bytes, actual state updates)
  - `0x021A0600` — S5 & S6 change messages (8 bytes, actual state updates)

**Bloc9 State Change Message Format** (CRITICAL - 8 bytes):
- Format documented in `scheiber/src/device_types.yaml` and tested in `test_bloc9_switch_change.py`
- **Bytes 0-3**: Lower switch (S1/S3/S5) data
  - Byte 0: Brightness level (0-255)
  - Byte 3, bit 0: ON/OFF state bit (0x01 = ON, 0x00 = OFF)
- **Bytes 4-7**: Higher switch (S2/S4/S6) data
  - Byte 4: Brightness level (0-255)
  - Byte 7, bit 0: ON/OFF state bit (0x01 = ON, 0x00 = OFF)
- **State determination**: `state = (state_bit == 1) OR (brightness > DIMMING_THRESHOLD)`
  - DIMMING_THRESHOLD = 2 (prevents LED flickering at extremes)
- **Example**: `021A06B8 Data=6b00110100000101`
  - S5: brightness=0x6b (107), state bit at byte[3]=0x01 → ON with brightness 107
  - S6: brightness=0x00 (0), state bit at byte[7]=0x01 → ON (but see quirk below)

**Bloc9 Hardware Quirks** (CRITICAL for correct behavior):
1. **Full brightness quirk**: When Bloc9 is ON without PWM (full brightness), it reports:
   - CAN message: `state_bit=1, brightness=0`
   - Must translate to: `brightness=255` for MQTT/Home Assistant
   - Implemented in `scheiber/light.py: update_state()`
   - Reason: MQTT convention is brightness 0 = OFF, brightness > 0 = ON
   
2. **Heartbeat vs State Updates**: 
   - Heartbeat messages (0x00000600) contain stale data and MUST NOT update device states
   - Only switch change messages (0x021X0600) should update states
   - Heartbeats are for device monitoring only (publish device info to observers)
   - Bug: If heartbeats update states, commands get immediately overridden
   
3. **Dimming Command Thresholds**:
   - Brightness 0-2: Send OFF command (0x00)
   - Brightness 3-252: Send PWM dimming command (0x11) with brightness value
   - Brightness 253-255: Send full ON command (0x01)

**Reading CAN Logs** (scheiber/src/tools/data/*.md):
- Logs are generated by `scheiber/src/tools/analyser.py`
- Format: `HH:MM:SS.mmm CANID [Description] HH HH HH HH HH HH HH HH`
- Change indicator lines show which bytes changed (^^ markers) - IGNORE these for data extraction
- Example from `command.md`:
  ```
  21:31:03.305 023606C0                      05 01 00 00
  21:31:03.380 021A06C0 X27 ID:8 S6,S5       00 00 00 00 00 00 01 01
  ```
  - First line: Command to turn ON switch 5 (S6, 0-indexed)
  - Second line: State update showing S6 ON (bytes 4-7: 00 00 01 01)
  
- Binary lines below hex show bit-level changes with color coding in terminal - ignore for data samples
- Focus on the hex data bytes for understanding message structure
- Sample data files:
  - `command.md`: Verified S5/S6 command protocol
  - `push_light_button.md`: Wireless button press sequences
  - `working_light.md`: Panel button interactions

**Verified Log Reading Examples** (from actual CAN dumps):
```
Command log sequence from command.md:
21:31:03.305 023606C0                      05 01 00 00
21:31:03.380 021A06C0 X27 ID:8 S6,S5       00 00 00 00 00 00 01 01
```
- Command (023606C0): Switch 5 (S6, 0-indexed), mode 0x01 (ON), data: `05 01 00 00`
- Response (021A06C0): S6 state update, 8 bytes: `00 00 00 00 | 00 00 01 01`
  - Bytes 0-3 (S5): brightness=0, state_bit=0 → OFF
  - Bytes 4-7 (S6): brightness=0, state_bit at byte[7]=1 → ON (full brightness quirk: becomes 255)

```
PWM dimming sequence from command.md:
21:32:00.780 023606C0                      04 01 00 00
21:32:00.786 021A06C0 X27 ID:8 S6,S5       0E 00 11 01 00 00 00 00
```
- Command: Switch 4 (S5, 0-indexed), mode 0x01 (ON)
- Response: S5 with PWM, data: `0E 00 11 01 | 00 00 00 00`
  - Bytes 0-3 (S5): brightness=0x0E (14), state_bit at byte[3]=1 → ON with brightness 14
  - Bytes 4-7 (S6): brightness=0, state_bit=0 → OFF
  - Note: byte[2]=0x11 appears in some messages but is not part of the state encoding

```
Wireless button press from push_light_button.md:
02:44:00.495 021A06B8 X26 ID:7 S5 & S6   3F 00 11 01 00 00 01 01
```
- S5/S6 state update for device 7 (bus_id from arbitration ID low byte)
- Bytes 0-3 (S5): brightness=0x3F (63), state_bit=1 → ON with brightness 63
- Bytes 4-7 (S6): brightness=0, state_bit=1 → ON (full brightness quirk: becomes 255)

**Layered Architecture** (CRITICAL - must be respected):
```
MQTT/HA Layer (devices.py)
    │ uses observer pattern
    ↓
Hardware Layer (scheiber_device.py)
    │ uses python-can
    ↓
CAN Bus
```
- **Hardware changes go in scheiber_device.py**: CAN protocol, device behavior, transitions, effects
- **MQTT changes go in devices.py**: Topics, discovery, entity config, Home Assistant integration
- **Never mix layers**: Hardware code shouldn't know about MQTT; MQTT code shouldn't implement CAN protocol
- **Observer pattern**: MQTT handlers subscribe to hardware devices via callbacks, not direct polling
- **Command delegation**: MQTT handlers call hardware device methods (set_brightness, fade_to, flash), don't send CAN directly

Agent coding rules for this repo
- Follow existing style (snake_case functions, concise helpers in `scheiber/src`).
- When changing code that opens `can.interface.Bus`, always open in a try/finally and call `bus.shutdown()` in `finally`.
- Use `apply_patch` for edits (small focused patches). Don't reformat whole files.
- **Respect layer boundaries**: Hardware features in scheiber_device.py, MQTT/HA integration in devices.py
- **Use hardware API**: For new device commands, add methods to device class (e.g., Bloc9Device), not in MQTT handler
- Avoid touching hardware-specific code unless the change is clearly safer (e.g., better error handling or clear abstractions). When in doubt, add a small wrapper or feature-flag.
- **Version management**: After making any code changes, update both version AND changelog:
  1. Update the `version` field in `scheiber/config.yaml` following semantic versioning (semver):
     - **PATCH** (0.0.X): Bug fixes, small tweaks, no API changes
     - **MINOR** (0.X.0): New features, backward-compatible changes (new parameters with defaults, new optional functionality)
     - **MAJOR** (X.0.0): Breaking changes (API changes, removed functionality, changed behavior, Home Assistant device structure changes)
     - Example: `0.5.8` → `0.5.9` for bug fix, `0.5.8` → `0.6.0` for new feature, `0.5.8` → `1.0.0` for breaking change
  2. Update `scheiber/CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format:
     - Move relevant items from `[Unreleased]` section to new version section
     - Add new version header: `## [X.Y.Z] - YYYY-MM-DD`
     - Use ISO 8601 date format (YYYY-MM-DD)
     - Categorize changes under: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`
     - Write entries for humans, not commit logs - focus on user-facing impact
     - Update version comparison links at bottom of file
     - Keep `[Unreleased]` section at top for tracking upcoming changes

**Home Assistant Device Structure (v4.0.0+)**:
- All entities (lights, switches, sensors) belong to a single unified "Scheiber" device in Home Assistant
- Device identifier: `scheiber_system`
- This simplifies entity naming: entities become `light.scheiber_<name>` instead of `light.<name>_<name>`
- The unified device appears as "Scheiber - Marine Lighting Control System" in Home Assistant

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
