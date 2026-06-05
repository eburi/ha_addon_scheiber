# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [6.11.1] - 2026-06-05

### Fixed
- Increased the setup browser idle timeout from 15 seconds to 15 minutes so Setup Helper findings, discovery, and inspector state are not discarded during short pauses such as checking the manual

## [6.11.0] - 2026-06-05

### Added
- Added Bloc9 `pulse` outputs that publish to Home Assistant as button entities for momentary trigger-style channels such as relay impulses for door or other external controllers

### Changed
- The Setup Helper now recognizes quick ON->OFF self-reset behaviour during tap captures and suggests pulse mappings instead of forcing every non-dimming output into the light/switch model
- Reusing the same `entity_id` across multiple Bloc9 pulse outputs now creates one logical Home Assistant button, matching the existing logical light and switch grouping model

## [6.10.8] - 2026-06-05

### Added
- Added a guided **Setup Helper** tab to the setup UI with countdown-based press/release and press/hold workflows for learning which Bloc9 outputs react to a physical button

### Changed
- Bloc9 output configuration now allows the same light or switch `entity_id` to be reused across multiple outputs so one logical Home Assistant entity can represent distributed loads such as underwater lights

## [6.10.7] - 2026-05-30

### Fixed
- Fixed setup-browser idle cleanup so frontend-only discovery shutdown no longer crashes when the last browser session expires before Bloc9 discovery has ever been started

## [6.10.6] - 2026-05-29

### Fixed
- Hardened the setup Web UI base-path handling so the direct `/` and `/inspect` pages keep resolving API requests correctly even without Home Assistant ingress, while still preserving ingress-aware URLs

## [6.10.5] - 2026-05-29

### Fixed
- Fixed setup Web UI startup under Home Assistant ingress so first-load API calls and the embedded inspector use ingress-aware URLs instead of sometimes fetching the HTML shell and failing with a JSON parse error

## [6.10.4] - 2026-05-29

### Fixed
- MQTT discovery for lights, switches, and sensors now publishes names derived from each configured entity slug, so new Home Assistant entity ids are more specific on first discovery

## [6.10.3] - 2026-05-26

### Fixed
- Bloc7 raw sender discovery now exposes a decimal voltage draft from bytes 4-5, so battery-style values are no longer limited to the coarse integer from byte 5 alone
- Bloc7 setup cards now let fixed matcher-based sensors change between level, voltage, and the other supported sensor types instead of locking discovered mappings to the original draft type

## [6.10.2] - 2026-05-21

### Fixed
- Updated the built-in MCP server to negotiate the current `2025-11-25` MCP protocol version used by newer remote HTTP clients such as Zed
- Added modern MCP HTTP response behavior for protocol-version headers, explicit non-POST `/mcp` handling, and prompt discovery support so remote clients can complete initialization reliably

## [6.10.1] - 2026-05-20

### Fixed
- Bloc9 live output testing now only exposes and sends brightness values after an output is explicitly marked as a **Light**
- Bloc9 live test controls now default light outputs to full-on brightness so a plain **On** test does not send PWM unless the operator deliberately lowers the slider

## [6.10.0] - 2026-05-19

### Added
- Added shared Scheiber route decoding for bus/segment address bytes so Bloc7, Bloc9, and SourceSelector observations can be grouped by route without conflating device families
- Added read-only SourceSelector AC measurement support with voltage and frequency sensors for observed `0x02040Bxx` frames
- Added protocol-aware setup and MCP candidate discovery for Bloc7, SourceSelector, and ambiguous status frames
- Added frequency, current, state-of-charge, and raw sensor types for matcher-based sensor devices

### Changed
- Bloc7 configuration now supports nonzero `segment_id` values while preserving existing manual matcher-based sensor configs
- CAN inspector status classification now distinguishes message families instead of labeling every `0x000006xx` status frame as a verified Bloc9 heartbeat

## [6.9.8] - 2026-05-19

### Fixed
- Bloc7 tank level values are now shown and advertised as percentages instead of liters in the setup UI and MQTT Discovery

## [6.9.7] - 2026-05-19

### Changed
- Bloc9 cards and Bloc9 output sections in the setup UI now start collapsed by default, so expandable sections stay closed until the operator opens them

## [6.9.6] - 2026-05-18

### Fixed
- Fixed Bloc7 sensor construction so tank and voltage sensors no longer go through the Bloc9 output constructor path, which removes the `Output.__init__()` error when adding a Bloc7 from the web UI

## [6.9.5] - 2026-05-18

### Fixed
- Fixed Bloc7 setup saves so runtime matcher construction now unpacks both `pattern` and `mask`, which removes the missing-`mask` error when adding a Bloc7 from the web UI

## [6.9.4] - 2026-05-18

### Changed
- Reworked Bloc7 setup discovery around per-message cards so a discovered arbitration ID now configures both reported channels in one place instead of spawning one-sensor suggestion flows
- Simplified mapped Bloc7 sensor editing by keeping matcher and byte mapping fixed for discovered channels while still showing live readings to help identify tanks during setup

### Fixed
- Bloc7 MQTT discovery for configured fluid sensors now publishes Home Assistant volume metadata with liters and measurement state classification

## [6.9.3] - 2026-05-18

### Fixed
- Added browser heartbeats for the setup web UI so frontend-only services no longer keep running after the last browser page goes away
- Stopped live Bloc9 discovery and standalone CAN inspector capture automatically when all setup browser sessions have expired or disconnected

## [6.9.2] - 2026-05-18

### Fixed
- Stopped the setup editor from re-rendering the visible tab on every keystroke and from unrelated background polling, which makes Bloc9 and Bloc7 field editing responsive again instead of fighting focus/caret resets
- Prevented hidden-tab background refreshes from rebuilding the active tab, reducing the gradual slowdown seen while leaving the setup page open

## [6.9.1] - 2026-05-18

### Changed
- CAN Bus Inspector now lets operators switch live byte rendering between hexadecimal and unsigned decimal without leaving the page
- Bloc9 setup now raises toast feedback for live output state changes while the Bloc9 tab is open, so discovery activity is visible even when the changed card is further down the page
- Bloc9 output sections now have a clearer bordered separation, and each output's current state header stays sticky while scrolling through long cards

## [6.9.0] - 2026-05-17

### Changed
- Refactored the setup UI into a mobile-first tabbed workflow with a sticky **Setup** header, bridge health/error indicator, horizontally scrolling navigation, and toast-style action feedback
- Reworked Bloc9 setup into direct-edit cards that combine discovery, live output testing, and saved configuration so discovered devices can be added and configured devices can be updated in place
- Reworked Bloc7 setup into card-based saved drafts plus live candidate promotion, while keeping the CAN inspector available as the third setup tab

## [6.8.1] - 2026-05-17

### Fixed
- Inspector bit-level diff highlighting now maps `bit 0` through `bit 7` to the displayed `7 … 0` bit columns correctly, so changed bits are marked on the right byte positions instead of mirrored

## [6.8.0] - 2026-05-17

### Added
- First-class Bloc7 support in the validated configuration workflow, including manual matcher-based voltage and level sensors
- Bloc7 candidate analysis in the setup UI and MCP server so likely CAN frames can be promoted into provisional sensor drafts

### Changed
- The setup editor now supports both Bloc9 output devices and Bloc7 sensor devices from the same ingress workflow
- Bloc7 runtime loading now accepts the new unified `sensors:` format while remaining compatible with the older `voltages:` and `levels:` sections

### Fixed
- MQTT sensor entities now expose the same publish/update hooks the bridge expects, so configured sensors are announced and republished reliably

## [6.7.2] - 2026-05-17

### Added
- Home Assistant add-on store assets with dedicated `icon.png` and `logo.png` branding for the Scheiber integration
- Add-on-specific `README.md` and `DOCS.md` files so the store card and documentation tab now present focused Home Assistant setup guidance

### Changed
- Refreshed the add-on metadata and repository display name to better match the Home Assistant add-on presentation

## [6.7.1] - 2026-05-17

### Fixed
- Restored Home Assistant ingress access by always binding the management server to `0.0.0.0` when it is enabled
- Stopped starting the add-on management server when `web_ui_enabled` is off, so the bridge-only mode avoids the extra web runtime entirely

### Removed
- Removed the unused add-on option `web_ui_expose_network`; the setup UI is now simply on or off via `web_ui_enabled`

## [6.7.0] - 2026-05-17

### Added
- Optional MCP server support on the add-on management runtime so AI tools can read/write validated Scheiber configuration and inspect live CAN traffic for setup and reverse engineering
- New add-on option `mcp_server_enabled` to turn the MCP endpoint on only when it is needed

### Changed
- The management runtime now starts whenever either the setup UI or MCP server is enabled, allowing MCP to reuse the same validated config workflow and shared CAN listener
- Add-on metadata, docs, and startup logs now warn that MCP exposes configuration editing and CAN inspection and should only be enabled temporarily
## [6.6.3] - 2026-05-17

### Changed
- The add-on web UI now binds to loopback by default so Home Assistant ingress keeps working without exposing the setup interface on the host network
- When the setup UI is disabled, the add-on now skips the web server process entirely and runs the CAN-to-MQTT bridge directly

### Added
- New add-on option `web_ui_enabled` allows operators to disable the setup UI server after setup and run the bridge without starting the non-production web process
- New add-on option `web_ui_expose_network` allows operators to opt in to binding the setup UI on all host interfaces when direct network access is required

## [6.6.2] - 2026-05-17

### Fixed
- Inspector now annotates known Bloc9 heartbeats, state updates, and command frames with human-readable summaries directly in the arbitration-ID list
- Inspector filtering now supports masked arbitration-ID matching, decoded-text matches, and hiding known traffic so unknown frames are easier to isolate during reverse engineering

## [6.6.1] - 2026-05-17

### Added
- Inspector arbitration-ID rows now show decoded summaries for known Bloc9 traffic, including route-aware device labels and extracted output state or command details under the raw CAN ID
- Inspector filtering now supports an optional bitmask, so IDs can be matched with expressions equivalent to `(arbitration_id & mask) == (filter & mask)`

### Changed
- Inspector filtering can now hide all rows whose latest frame matches a known message pattern, making it easier to focus on unknown traffic during reverse engineering

## [6.6.0] - 2026-05-16

### Added
- Bloc9 devices can now be configured with an optional `segment_id`, allowing the same local `bus_id` to be used on different routed Scheiber segments without collisions

### Changed
- Segment-aware Bloc9 routing now flows through discovery, saved configuration, runtime device identity, state persistence, MQTT topics, and MQTT unique IDs
- Native/local devices keep the existing `bus_id` identity, while routed devices use `bus_id_segment_id` slugs such as `3_2` in the setup UI and MQTT paths
- The setup UI now labels discovered routed Bloc9 devices as `Bloc9 #bus_segment` and saves `segment_id` when promoted into configuration
- Bloc9 config validation now enforces the hardware-addressable `bus_id` range of `0..15`

### Fixed
- Light fade transitions no longer overshoot their configured duration by an extra timing step at completion

## [6.5.0] - 2026-05-16

### Added
- Bloc9 configuration files can now persist saved output labels under `outputs:` even before an output is assigned as a light or switch

### Changed
- The setup editor now keeps named-but-unassigned Bloc9 outputs in the saved draft so a newly added device can be documented before each output gets its final role
- Config validation now requires `entity_id` only after an output is assigned as a light or switch, while still preserving the saved output name for unassigned outputs
- Device summaries in the setup UI now show saved unassigned outputs instead of dropping them from view

## [6.4.5] - 2026-05-16

### Added
- Discovery now exposes a **segment suffix** for Bloc9 candidates when the arbitration ID uses non-zero low bits, so forwarded or bridged targets can be distinguished from native local-bus devices during setup

### Changed
- The setup UI labels native vs suffix-routed Bloc9 candidates explicitly and sends live test commands with the same suffix bits seen in discovery traffic
- Forwarded or suffix-routed discovery candidates remain testable in the UI but are not yet promotable into saved config, avoiding misleading single-bus configuration entries

### Fixed
- Bloc9 discovery and live test control now understand remote status frames such as `0x0216069A`, preserving the normal payload decode while treating the low 3 arbitration-ID bits as a routing suffix
- Live discovery keeps local and routed variants of the same Bloc9 bus ID separate instead of collapsing them into one candidate

## [6.4.4] - 2026-05-16

### Added
- **Download history**: "⬇ Download" button in the message detail panel exports the history as a candump log file (`candump_<ARBID>.log`), format `(timestamp.ffffff) <interface> <ARBID>#<HEXDATA>`, ready for offline analysis

### Changed
- Clear button now keeps the detail panel open for the selected arbitration ID; history is cleared but the panel stays visible so the user can immediately see new traffic for that ID
- Inspector snapshot API now includes `can_interface` field (used as the channel name in downloaded candump logs)

## [6.4.3] - 2026-05-16

### Fixed
- Clear button now closes and resets the message detail panel before restarting capture

## [6.4.2] - 2026-05-16

### Fixed
- Inspector no longer polls for updates while capture is stopped; the table and detail panel are now static (selectable/copyable) once stopped. Polling resumes only when capture is restarted.

## [6.4.1] - 2026-05-16

### Fixed
- Inspector bit change positions now use standard LSB=0 convention; previously bit 0 was treated as MSB, so a change from `0x10` to `0x20` was reported as `B4[2,3]` instead of the correct `B4[4,5]`

## [6.4.0] - 2026-05-16

### Added
- **CAN Bus Inspector**: new `/inspect` page for reverse engineering and protocol discovery
  - Captures all raw CAN messages (not just Bloc9) while the bridge is running
  - Summary table of every arbitration ID seen, with message count, frequency (Hz), relative last-seen time, DLC, and last data bytes (changed bytes highlighted in amber)
  - Sortable columns (click any header) and a live text filter; "Changes only" checkbox to focus on IDs whose data is actively changing
  - Click any row to open a detail panel showing bit-level diff (prev → curr) for every byte with individual changed bits marked, plus a 30-message history table with timestamps and per-entry bit annotations
  - Start / Stop / Clear controls; clear resets the session without leaving the page
  - New `CanInspector` service (`scheiber_web/inspector.py`) and REST endpoints: `GET /api/inspect`, `POST /api/inspect/start`, `POST /api/inspect/stop`, `GET /api/inspect/detail/<hex_id>`
- **Inspect button** in the Setup page hero header, linking to the new inspector
- **Mobile-optimised UI** across both the Setup and Inspector pages
  - Minimum 44 px touch targets on all buttons, inputs, and selects
  - Hero and section headers stack vertically on ≤ 880 px; actions wrap instead of overflow
  - Device card headers and inline action buttons wrap and stretch on phones
  - Filter row stacks and goes full-width on narrow screens
  - "Freq (Hz)" and "DLC" columns hidden on phones to keep the inspector table readable without horizontal scroll
  - History table gets an `overflow-x: auto` scroll container with momentum scrolling on iOS
  - Reduced page and card padding on phones; scaled-down heading sizes

## [6.3.6] - 2026-05-16

### Added
- Expandable output controls on discovered Bloc9 candidates: click "▼ Test outputs" to reveal S1–S6 rows
- Each output row has a function selector (—, Switch, Light) and On/Off buttons; Light also shows a brightness slider (0–255)
- Commands are sent live to the CAN bus so admins can identify and validate outputs before configuring them; nothing is persisted
- New `POST /api/discovery/control` endpoint and `BridgeRuntimeController.send_bloc9_command()` method backing the controls



### Fixed
- Fixed all fetch requests being blocked by Chrome's Private Network Access (PNA) policy when HA is accessed over HTTP on a `.local` mDNS hostname; Flask now responds with `Access-Control-Allow-Private-Network: true` on all responses and handles OPTIONS preflights correctly

## [6.3.4] - 2026-05-15

### Changed
- Discovery now runs indefinitely until explicitly stopped (no timeout)
- Replaced Start/Stop discovery buttons with a single toggle button that shows "Start discovery" or "Stop discovery" based on the current state

## [6.3.3] - 2026-05-15

### Changed
- Discovery UI now shows an explicit **Bus ID** label for each discovered Bloc9 candidate, extracted from the arbitration ID low byte

## [6.3.2] - 2026-05-15

### Fixed
- Fixed static asset paths under HA ingress: replaced the `before_request` hook (which ran after Flask's URL adapter was created) with a WSGI middleware that sets `SCRIPT_NAME` from `X-Ingress-Path` before the request context is pushed, so `url_for('static', ...)` generates correctly prefixed URLs

## [6.3.1] - 2026-05-15

### Fixed
- Fixed static assets (CSS, JS) returning 404 under Home Assistant ingress by reading the `X-Ingress-Path` header and setting Flask's `SCRIPT_NAME` accordingly, so `url_for('static', ...)` generates correctly prefixed URLs

## [6.3.0] - 2026-05-15

### Added
- Added a built-in Home Assistant ingress web interface for Scheiber setup and configuration
- Added a Bloc9 discovery mode that watches live CAN traffic for known state-update arbitration IDs and suggests candidate bus IDs
- Added a structured config editor API and setup UI for creating and editing Bloc9 device mappings

### Changed
- The add-on now starts the web interface as the primary process and manages the MQTT bridge as a shared runtime behind it
- Configuration loading now uses strict validation and canonical YAML serialization for `scheiber-config.yaml`

## [6.2.16] - 2026-05-14

### Removed
- Removed the `run_dev_version` add-on option and the dead legacy bridge startup branch

## [6.2.15] - 2026-05-14

### Changed
- Removed the unused `build_from` manifest section now that the Dockerfile derives the Home Assistant base image directly from `BUILD_ARCH`

## [6.2.14] - 2026-05-14

### Fixed
- Switched add-on Docker base image selection from `BUILD_FROM` to `BUILD_ARCH`, which Home Assistant Supervisor reliably passes during build
- Fixes installation failure where `FROM $BUILD_FROM` was blank on aarch64 builds

## [6.2.13] - 2026-05-14

### Fixed
- Added `build_from` architecture mapping in add-on manifest so Home Assistant provides `BUILD_FROM` during Docker builds
- Fixes add-on installation failure with `FROM $BUILD_FROM` resolving to a blank base image

## [6.2.12] - 2026-03-08

### Changed
- Standardized configuration filename to `scheiber-config.yaml` in docs, CLI help text, and add-on defaults
- Moved sample config from repository root to `docs/examples/scheiber-config.yaml`

### Removed
- Removed legacy root `scheiber.yaml` file to avoid format confusion

## [6.2.11] - 2025-12-13

### Added
- **Automatic Migration System**: run.sh now automatically runs migration scripts on startup
  - Migration scripts in `src/migrate/` directory
  - Supports both Python (.py) and Shell (.sh) scripts
  - Tracks applied migrations in `${DATA_DIR}/.migrations_applied`
  - Migrations run once, in alphabetical order
  - Startup fails if migration fails (safety mechanism)

### Fixed
- **State File Migration**: Added backward compatibility for state file format
  - System now tries entity_id first, then falls back to old s1-s6 format
  - Migration script `001_migrate_state_keys_to_entity_id.py` automatically converts old format to new
  - Creates timestamped backup before migration
  - Idempotent (safe to run multiple times)
  - Fixes issue where devices didn't initialize with persisted state after v6.2.9 upgrade

### Technical Details
- Migration framework in `run.sh` with proper error handling
- Python migrations run with activated virtualenv
- Shell migrations receive DATA_DIR and CONFIG_FILE as arguments
- Comprehensive README.md in migrate/ directory with examples and best practices

## [6.2.10] - 2025-12-13

### Changed
- Smart initial state publishing: System now checks existing MQTT retained state before publishing on startup
- Only publishes initial state if: (1) no retained message exists, (2) retained message is old (>60s), or (3) state differs from hardware
- Reduces unnecessary MQTT traffic on restarts when state already matches
- Added detailed logging to track initial state decisions (retained match, stale state, missing state, state mismatch)
- Timeout after 2 seconds ensures state is published even if MQTT broker doesn't respond with retained message

### Technical Details
- Uses `message_callback_add()` to temporarily subscribe to state topic during initialization
- Compares hardware state with MQTT retained state before deciding to publish
- Logs explain clearly what decision was made and why (matching, old, missing, or different)
- Maintains compatibility with existing callback architecture (doesn't break tests)

## [6.2.9] - 2025-12-13

### Changed
- **BREAKING: State-First Initialization Architecture**: Complete redesign of startup sequence
  - Persisted state now loaded BEFORE device creation (not after)
  - Devices initialize with correct state from the beginning
  - MQTT handlers no longer publish initial state on creation
  - State only published when CAN messages arrive (natural ~1 second delay)
  - Prevents spurious "all OFF" state on restart
  - Eliminates unnecessary MQTT traffic during startup

### Fixed
- **Startup Behavior**: System no longer publishes all entities as OFF then restores
  - Previous flow: Create devices (OFF) → publish OFF → restore state → republish
  - New flow: Load state → create devices with state → publish only on CAN updates
  - Logs show: "Initialized {name} from persisted state: brightness=X, state=Y"
  - Discovery and availability still published immediately
  - Actual state waits for CAN confirmation (heartbeat messages)

### Technical Details
- `create_scheiber_system()` now calls `_load_state()` before `_create_devices()`
- `Bloc9Device.__init__()` accepts `initial_state` parameter
- Lights and switches initialize internal `_state` and `_brightness` from persisted data
- No CAN commands sent during initialization (unless `initial_brightness` in config)
- State keys changed from "s1-s6" to entity_id for consistency
- `ScheiberSystem.start()` no longer calls `_load_state()` (already loaded)
- All 109 tests passing with new architecture

## [6.2.8] - 2024-12-13

### Fixed
- **Light State Publishing**: Fixed incomplete MQTT state messages for lights
  - Light state updates now always publish both `state` and `brightness` fields
  - Previously only published changed fields (e.g., `{"brightness": 36}` without `state`)
  - Home Assistant requires both fields for proper entity state display
  - Now publishes complete state: `{"state": "ON", "brightness": 36}`
  - Fixes issue where light entities showed unknown state in Home Assistant UI

## [6.2.7] - 2024-12-13

### Fixed
- **Non-optimistic Switch Behavior**: Proper implementation of state updates only after CAN confirmation
  - Switch MQTT handler waits for CAN confirmation before publishing state to MQTT
  - `Switch.set()` sends CAN command without updating internal state
  - `Switch.update_state()` (called when CAN message received) updates state and notifies observers
  - MQTT handler publishes state only when observer callback triggered by CAN message
  - Logging added for debugging: command sending, CAN confirmation, and state updates
  - Prevents state desync between Home Assistant and physical hardware
  - ~100ms latency between MQTT command and state update (typical CAN response time)

### Added
- Comprehensive integration test suite for switch state confirmation flow
  - Test MQTT command → CAN command → CAN confirmation → MQTT state update
  - Test physical button press → CAN message → MQTT state update
  - Test discovery config with `optimistic: false`
  - All 109 unit tests passing

## [6.2.6] - 2024-12-13

### Fixed
- **Switch State Updates**: Restored optimistic state updates in `Switch.set()` method
  - Switch now updates state immediately when MQTT command received
  - Still validates with CAN confirmation via `update_state()`
  - Only publishes to MQTT if state actually changes (prevents duplicate notifications)
  - Fixes issue where switches didn't respond to MQTT commands
  - Physical button presses still trigger MQTT updates via CAN messages
- Optimistic updates work like lights: immediate feedback with CAN validation
- All 74 unit tests passing

## [6.2.5] - 2024-12-13

### Fixed
- **Switch MQTT Format**: Corrected switch entity MQTT schema for Home Assistant compatibility
  - Removed `"schema": "json"` from discovery config (switches use simple payload format)
  - Added `payload_on`, `payload_off`, `state_on`, `state_off` fields
  - State now published as plain "ON"/"OFF" instead of JSON `{"state": "ON"}`
  - Commands parsed as plain "ON"/"OFF" strings
  - Matches Home Assistant standard switch format
- **Non-optimistic Updates**: Switch state now only updates after CAN confirmation
  - Removed optimistic state update from `Switch.set()` method
  - State changes only occur when CAN message confirms the change
  - Ensures physical button presses update MQTT correctly
  - Observer notifications only on actual state changes from CAN bus
- Updated tests to reflect non-optimistic behavior
- All 74 unit tests passing

## [6.2.4] - 2024-12-13

### Fixed
- **AttributeError**: Added default `get_sensors()` method to `ScheiberCanDevice` base class
- Bridge was calling `get_sensors()` on all devices, but only `Bloc7Device` implemented it
- `Bloc9Device` now safely returns empty list when bridge queries for sensors
- Consistent API: all devices now have `get_lights()`, `get_switches()`, and `get_sensors()` methods
- All 74 unit tests passing

## [6.2.3] - 2024-12-13

### Fixed
- **Module Import Error**: Removed non-existent `helpers` module dependency from `sensor.py`
- Refactored `MQTTSensor` to use inline implementations matching `MQTTLight` and `MQTTSwitch` patterns
- Added missing `entity_id`, `get_value()`, `device_class`, and `icon` attributes to Bloc7 sensor classes
- Updated sensor observer pattern to pass state dictionary instead of sensor instance
- Fixed sensor constructor signatures to accept `entity_id` parameter
- All 74 unit tests passing

## [6.2.2] - 2024-12-13

### Fixed
- **Critical Syntax Error**: Fixed missing closing brace in `Switch.store_to_state()` that prevented module loading
- **Attribute Name Errors**: Fixed incorrect references to `send_command_func` and `notify_observers` (should be `_send_command_func` and `_notify_observers`)
- Removed orphaned code fragment in `switch.py` from previous refactoring
- All 74 unit tests now passing

## [6.2.1] - 2024-12-13

### Changed
- **Refactored State Persistence**: Improved encapsulation following OOP principles
  - `DimmableLight` and `Switch` now own their state persistence logic
  - Added `restore_from_state()` and `store_to_state()` methods to both classes
  - `Bloc9Device` now delegates state operations to individual outputs instead of directly accessing internal attributes
  - Better encapsulation: state management contained within each output class
  - Easier to extend with new output types in the future
- Added `device_class: "switch"` to MQTT switch discovery config for proper Home Assistant categorization

## [6.2.0] - 2024-12-13

### Added
- **Bloc7 Device Support**: New configuration-driven module for analog sensor monitoring
  - `Voltage` and `Level` sensor types for tank levels and voltages
  - Each sensor configured with its own matcher and value extraction rules (start byte, bit length, endianness, scale)
  - `ValueConfig` class handles flexible data extraction from CAN messages
  - State persistence for sensor values
  - `MQTTSensor` bridge for Home Assistant integration with proper device classes
  - Example configuration in `scheiber-config.yaml`
- Analysis tool: `analyze_bloc7.py` for discovering Bloc7 CAN message patterns
  - Correlates CAN bus traffic with MQTT sensor values
  - Identifies voltage and tank level encodings automatically

### Changed
- **Refactored Bloc7 Integration**: Removed hardcoded message routing
  - Bloc7Device now properly implements `get_matchers()` like Bloc9Device
  - Integrates with existing matcher system instead of special-case handling
  - Removed `isinstance(device, Bloc7Device)` checks from `system.py`
  - Cleaner, more maintainable architecture
- Simplified `process_message()` interface across all devices
  - Removed unused `matched_property` parameter from abstract method
  - Updated all device implementations (Bloc9Device, Bloc7Device)
  - Updated documentation in `IMPLEMENTATION.md`
- Improved Home Assistant sensor configuration
  - Voltage sensors use proper `device_class: "voltage"`
  - Tank levels use `icon: "mdi:gauge"` and `state_class: "measurement"`
  - Removed workaround of using `power_factor` device class

## [6.1.1] - 2024-12-13

### Added
- Debug logging for CAN message routing at output level
  - Switch outputs log: `Switch 'Name' (SX) received matched message: arbitration_id=0xXXXXXXXX, state=True/False`
  - Light outputs log: `Light 'Name' (SX) received matched message: arbitration_id=0xXXXXXXXX, state=True/False, brightness=XXX`
  - Helps track which outputs are processing which CAN messages during runtime
  - Uses existing logger hierarchy: `Bloc9.{device_id}.{output_name}`

### Changed
- Moved `config_loader.py` to `archive/` directory (only used by archived v5 code)
  - v6 uses inline YAML loading in `scheiber/__init__.py`
  - Cleaner src directory structure

## [6.1.0] - 2024-12-13

### Fixed
- **CRITICAL BUG FIX**: Fixed cross-device message pollution where switches on one device affected ALL devices
  - Root cause: Matcher mask was 0xFFFFFF00, ignoring device ID byte in low 8 bits
  - Example: Message 0x021806D0 (device 10, S3/S4) matched all devices (1-10)
  - Fix: Changed matcher mask to 0xFFFFFFFF to include full 32-bit arbitration ID
  - Device ID encoding uses `(device_id << 3) | 0x80` for all message types
  - Added comprehensive test suite (6 tests) verifying message routing isolation

### Changed
- **BREAKING ARCHITECTURE**: Removed `property` field from Matcher class
  - Matchers now use only pattern/mask for matching
  - Direct dispatch: `_matcher_to_outputs` maps arbitration_id → List[Output]
  - Outputs (Switch/DimmableLight) define their own matchers via `get_matchers()`
  - `process_message(msg)` signature changed from `process_message(msg, matched_property)`
  - Cleaner architecture: outputs own their message patterns, not device
- Created `Output` base class for Switch and DimmableLight
  - Shared CAN message decoding via `get_state_from_can_message()`
  - Common observer pattern implementation
  - Each output defines its own matchers
- Bloc9Device delegates matcher creation to individual outputs
  - Removed hardcoded STATUS_MATCHERS constant
  - Removed manual switch_nr lookups (_switch_nr_to_light, _switch_nr_to_switch)
  - Direct dispatch more efficient than property-based routing
- `get_matchers()` now called automatically in `Bloc9Device.__init__()`
  - Ensures `_matcher_to_outputs` mapping is built before message processing
  - Tests no longer need to manually call `get_matchers()`

### Added
- New test file `test_message_routing.py` with 6 comprehensive routing tests:
  - `test_message_only_affects_target_device`: Core bug verification
  - `test_multiple_devices_receive_own_messages`: Multiple device isolation
  - `test_device_ignores_heartbeat_from_other_devices`: Heartbeat routing
  - `test_command_echo_only_processed_by_sender`: Command echo handling
  - `test_real_world_scenario_from_can_names_csv`: Real CAN ID validation
  - `test_matcher_registration_isolation`: Matcher mapping verification
- Debug utility `list_matchers.py`: Lists all matchers registered by system from config
- Total test count increased from 99 to 105 tests

## [6.0.0] - 2024-12-13

### Changed
- **BREAKING**: New modular architecture (can-mqtt-bridge) is now the default
- V5 code moved to `src/archive/` directory
- V5 (mqtt_bridge.py) now runs only when `run_dev_version: true` is set

### Added
- Effect storage: Home Assistant effect selection now stored as default easing for transitions
  - Sending `{"state":"ON","effect":"ease_in_cubic"}` stores the effect without changing light state
  - Subsequent brightness changes use stored effect as easing function
  - Effect parameter with brightness creates smooth transition: `{"brightness":150,"effect":"ease_out_quad"}`
  - Explicit transition parameter overrides stored effect
- `_default_easing` attribute in `DimmableLight` (defaults to "ease_in_out_sine")
- Optional `effect` parameter in `DimmableLight.set()` method

## [5.7.8] - 2024-12-13

### Added
- Comprehensive test suite for `_process_switch_change()` with 16 tests:
  - Message format validation for S1/S2, S3/S4, S5/S6 pairs
  - Brightness and state bit parsing from 8-byte messages
  - Dimming threshold behavior
  - Bloc9 hardware quirk (state=ON + brightness=0 → brightness=255)
  - Mixed light/switch configurations
  - Observer notification on state changes
  - Short message handling
  - Actual bug report message validation
- All 100 tests passing (84 original + 16 new)

## [5.7.7] - 2024-12-13

### Fixed
- **CRITICAL**: Fixed switch state change message parsing to match actual 8-byte format
  - Previously read bytes 0-1 for brightness/state, causing incorrect parsing
  - Now correctly reads byte 0 for brightness and byte 3 bit 0 for state (lower switch)
  - Now correctly reads byte 4 for brightness and byte 7 bit 0 for state (higher switch)
  - This matches the format documented in device_types.yaml
  - Fixes state updates being reset to OFF after commands

### Added
- INFO-level logging for all switch state change messages showing CAN ID and data
- Warning when switch change messages are too short (< 8 bytes)

## [5.7.6] - 2024-12-13

### Added
- Comprehensive test suite for heartbeat behavior with 8 new tests:
  - `test_heartbeat_does_not_update_light_state`: Verifies heartbeats don't override light states
  - `test_heartbeat_publishes_device_info`: Verifies device info publication on heartbeat
  - `test_state_change_message_still_updates_state`: Ensures actual state change messages work
  - `test_heartbeat_after_command_does_not_reset`: Tests the specific brightness reset bug scenario
  - `test_heartbeat_with_no_configured_outputs`: Tests edge case with no outputs
  - `test_multiple_heartbeats_in_sequence`: Verifies repeated heartbeats don't affect state
  - `test_switch_not_affected_by_heartbeat`: Ensures switches also protected from heartbeat interference
  - `test_device_observer_pattern_for_heartbeat`: Tests device-level observer pattern
- Device-level observer pattern in `ScheiberCanDevice` base class for heartbeat events

### Changed
- All 84 tests passing (76 original + 8 new heartbeat tests)

## [5.7.5] - 2024-12-13

### Changed
- **Improved State Update Logging**: State updates from CAN bus to MQTT now log at INFO level instead of DEBUG
  - Light state updates: `Published state to homeassistant/scheiber/bloc9/7/s5/state: {"state": "ON", "brightness": 200}`
  - Switch state updates: `Published state to homeassistant/scheiber/bloc9/7/s1/state: {"state": "ON"}`
  - Makes it easier to verify that CAN messages are being received and processed
  - Helps diagnose issues with state synchronization between hardware and Home Assistant

- **Low-Priority Status Messages**: Changed to heartbeat-only, no longer used for state updates
  - Status message (`0x00000600`) is now only used as device heartbeat
  - Prevents stale heartbeat data from overriding actual switch state changes
  - Status messages now trigger device info publication to MQTT
  - Device info includes output configuration: `{"outputs": {"s1": "Main Light", "s2": "unknown", ...}}`

### Added
- **State Flow Test**: Added comprehensive test verifying CAN → Hardware → MQTT state propagation
  - Confirms observer pattern working correctly
  - Validates state updates are published with correct topics and payloads

- **Device-Level Observer Pattern**: Base device class now supports observers for device-level events
  - Enables publishing device info (output configuration) to MQTT
  - Heartbeat messages trigger device info updates
  - Foundation for future device-level monitoring features

### Fixed
- **State Override Issue**: Commands no longer get immediately overridden by heartbeat messages
  - Root cause: Heartbeat messages were being parsed as state changes
  - Solution: Heartbeat messages now only publish device info, not state updates
  - State updates only come from actual switch change messages (`0x021A0600` etc.)

## [5.7.4] - 2025-12-13

### Added
- **Retained Message Safety**: V6 MQTT bridge now validates retained commands to prevent stale command execution
  - Checks age of retained MQTT messages (5-minute threshold)
  - Ignores and clears commands older than 5 minutes
  - Prevents old commands from executing after server restart
  - Clears retained commands after successful execution
  - Added comprehensive test suite for retained message handling (8 tests)
  - Bridge passes `is_retained` and `timestamp` to command handlers
  - Both lights and switches implement message age validation

## [5.7.3] - 2025-12-13

### Fixed
- **CAN Message Processing**: Fixed IndexError when processing CAN messages for mixed light/switch configurations
  - Bloc9Device now uses switch_nr-to-object mapping instead of assuming list positions
  - Handles cases where S1-S6 outputs are configured as lights, switches, or not configured at all
  - Prevents crashes when receiving status messages for unconfigured outputs
  - Status messages now gracefully skip unconfigured outputs instead of throwing IndexError

## [5.7.2] - 2025-12-13

### Fixed
- **CAN Extended ID Support**: Fixed CAN message creation to use extended 29-bit arbitration IDs
  - Changed `is_extended_id=False` to `is_extended_id=True` in `ScheiberCanBus.send_message()`
  - Previously, 29-bit IDs like `0x023606B8` were truncated to 11 bits (`0x000006B8`)
  - CAN commands now correctly reach Bloc9 devices on the bus
  - Added `qos=1, retain=True` to all V6 MQTT publish calls for message persistence
  - Added comprehensive test suite for Bloc9 CAN command generation (10 tests)
  - Added integration test to verify `is_extended_id=True` flag on actual CAN messages

## [5.7.1] - 2025-12-12

### Fixed
- **Switch Discovery**: Added missing `get_switches()` method override in Bloc9Device
  - Switches are now properly exposed to MQTT bridge for discovery publishing
  - Previously, `get_switches()` returned empty list from base class despite switches being configured
  - All 16 configured switches now publish discovery configs correctly

## [5.7.0] - 2025-12-12

### Fixed
- **MQTT Topic Schema Compatibility**: Restored v5 MQTT topic structure to maintain entity persistence
  - Config topics now use entity_id: `{prefix}/light/{entity_id}/config`
  - State/command topics use switch identifier: `{prefix}/scheiber/{type}/{id}/s{n}/state`
  - unique_id maintains v5 format: `scheiber_{type}_{id}_s{n}`
  - Display names taken directly from hardware config (`hardware_light.name`)
  - Switch identifier generated from switch_nr: `f"s{switch_nr + 1}"`
  - Both light and switch entities updated for consistency
  - All 22 bridge tests updated with proper mocks and assertions

### Changed
- **Transition Controller Refactoring**: Complete OOP rewrite with progressive simplification
  - TransitionController and FlashController now use clean object-oriented design
  - Added TYPE_CHECKING imports for DimmableLight type hints
  - Controllers call `light._set_brightness(brightness, notify=False)` during transitions
  - Observers notified once at end of transition for efficiency
  - Removed unused parameters: switch_nr, on_step, property_name
  - Converted active_transitions dictionary to single `self.stop_event` property
  - Direct use of `self.stop_event` without intermediate variables
  - Inlined `_send_switch_command` in light.py for cleaner API

### Added
- **Flash Support in MQTT Discovery**: Advertise flash capability with configurable durations
  - `flash: true` in discovery payload
  - `flash_time_short: 2` seconds
  - `flash_time_long: 10` seconds
- **Comprehensive Test Coverage**: 45 tests total (23 hardware + 22 bridge)
  - 6 CAN message sequence tests verifying proper transitions with Scheiber edge case
  - 2 timing accuracy tests verifying transitions take expected duration (±100-150ms)
  - Tests use observer callbacks for proper completion detection
  - All easing functions tested with various parameters

## [5.6.0] - 2025-12-12

### Added
- **Easing Effects for Lights**: MQTT discovery now advertises all 13 easing functions from `easing.py`
  - Effect list includes: linear, ease_in_sine, ease_out_sine, ease_in_out_sine, ease_in_quad, ease_out_quad, ease_in_out_quad, ease_in_cubic, ease_out_cubic, ease_in_out_cubic, ease_in_quart, ease_out_quart, ease_in_out_quart
  - Users can select easing effect in Home Assistant UI for fade transitions
  - Command JSON accepts `"effect": "<easing_name>"` parameter alongside `"transition"`
  - Effect parameter passed to hardware layer's `fade_to()` method as `easing` argument
  - Defaults to `ease_in_out_sine` when no effect specified
  - Tests verify effect parameter is correctly applied and defaults work

## [5.5.0] - 2025-12-11

### Changed
- **MQTT Bridge Architecture**: Refactored to object-oriented design
  - New `MQTTLight` class handles all light-specific MQTT operations
  - New `MQTTSwitch` class handles all switch-specific MQTT operations
  - Each entity manages its own discovery config, state publishing, and command handling
  - Cleaner separation of concerns: entities know how to advertise themselves
  - Simplified `MQTTBridge` class - now just creates and manages entity instances
  - Topic matching delegated to individual entities via `matches_topic()` method
  - Command handling delegated to individual entities via `handle_command()` method
- **Switches use JSON schema**: Consistent with lights (v5.0.0+)
  - Switch states published as `{"state": "ON/OFF"}` instead of plain strings
  - Switch commands parsed as JSON like lights
  - Discovery config includes `"schema": "json"`

### Technical Details
- Bridge creates entity instances from hardware devices on startup
- Each entity subscribes to its hardware device's state changes
- Observer pattern maintained: hardware → entity → MQTT
- All 19 tests pass with refactored architecture

## [5.4.2] - 2025-12-11

### Fixed
- **MQTT Bridge**: Added missing `availability_topic` to Home Assistant discovery configs for lights and switches
  - Publishes "online" status for all entities on startup
  - Required for compliance with Home Assistant MQTT Discovery specification
  - Fixes check_mqtt.py test validation

## [5.4.1] - 2025-12-10

### Changed
- **v6 Preview Development**: Advanced DimmableLight component
  - Fixed `update_state()` to properly handle Bloc9 hardware quirk (full brightness reports as state=ON, brightness=0 → now translates to brightness=255)
  - Added debug logging for state changes with translation indicator
  - Ensures consistent MQTT reporting: brightness 0 = OFF, brightness > 0 = ON
- **v5 Stable**: No changes (production-ready, default)

## [5.4.0] - 2025-12-10

### Added
- **PREVIEW: New scheiber Python module** - First prototype with clean architecture
  - Factory pattern for initialization (`create_scheiber_system()`)
  - Modular structure: `can_bus.py`, `system.py`, `base_device.py`, `bloc9.py`, `light.py`, `switch.py`, `transitions.py`, `matchers.py`
  - Observer pattern for state notifications
  - Periodic state persistence (every 30s)
  - CAN bus statistics tracking
  - Read-only mode support
- **PREVIEW: can-mqtt-bridge** - Prototype MQTT bridge using scheiber module
  - Cleaner code (~280 lines vs 500+ in old bridge)
  - Home Assistant MQTT Discovery integration
  - JSON command schema for brightness, transitions, flash
  - Unified "Scheiber" device in Home Assistant
  - Observer-based state publishing (no polling)
  - **Note**: Not yet feature-complete, opt-in only
- **scheiber-cli tool**: Command-line interface for monitoring CAN bus
  - `listen` command for real-time message display
  - Config file support or auto-discovery
  - State persistence support
- **run_dev_version config option**: Toggle between preview and stable bridge
  - `true`: Run new can-mqtt-bridge (experimental)
  - `false`: Run old mqtt_bridge.py v5.3.6 (default, stable)
- **Comprehensive documentation**: IMPLEMENTATION.md with complete architecture details

### Changed
- Major architecture advancement for improved readability and maintainability
- Preview bridge uses different command-line arguments and config format

### Note
- This is a **preview release** showcasing the future v6.0.0 architecture
- New bridge is a prototype - not yet on par with v5.3.6 implementation
- Default remains stable v5.3.6 bridge for production use
- Opt-in to preview via `run_dev_version: true` for testing and feedback

## [5.3.6] - 2024-12-09

### Fixed
- Fixed brightness preservation for post-transition echoes (race condition where CAN echo arrives after transition cleanup)
- Fade-down commands now correctly detect current brightness even when transition has just completed
- Extended brightness preservation logic to handle echoes arriving microseconds after `active_transitions` cleanup

## [5.3.5] - 2024-12-09

### Fixed
- Brightness preservation during threshold-crossing echoes when active transitions exist
- Internal brightness state now maintained when CAN echo reports brightness=0 during fade transitions

## [5.3.4] - 2024-12-09

### Changed
- Improved fade transition timing and smoothness
- Enhanced brightness calculation for fade effects

## [5.3.3] - 2024-12-09

### Fixed
- Fade transition stability improvements

## [5.3.2] - 2024-12-09

### Fixed
- Transition cancellation safety improvements

## [5.3.1] - 2024-12-09

### Fixed
- Multi-device transition handling improvements

## [5.3.0] - 2024-12-09

### Added
- Fade transition effects (fade_in, fade_out, fade_to)
- Configurable transition durations via Home Assistant UI
- Smooth brightness transitions with easing functions

## [5.2.0] - 2024-12-08

### Changed
- Enhanced device detection and registration
- Improved MQTT topic structure

## [5.1.0] - 2024-12-08

### Added
- Initial stable release with core functionality
- CAN bus device support (Bloc9, S-series switches)
- Home Assistant MQTT Discovery integration
- Brightness control and dimming support

[Unreleased]: https://github.com/eburi/ha_addon_scheiber/compare/v6.11.1...HEAD
[6.11.1]: https://github.com/eburi/ha_addon_scheiber/compare/v6.11.0...v6.11.1
[6.11.0]: https://github.com/eburi/ha_addon_scheiber/compare/v6.10.8...v6.11.0
[6.10.8]: https://github.com/eburi/ha_addon_scheiber/compare/v6.10.7...v6.10.8
[6.10.7]: https://github.com/eburi/ha_addon_scheiber/compare/v6.10.6...v6.10.7
[6.10.6]: https://github.com/eburi/ha_addon_scheiber/compare/v6.10.5...v6.10.6
[6.10.5]: https://github.com/eburi/ha_addon_scheiber/compare/v6.10.4...v6.10.5
[6.10.4]: https://github.com/eburi/ha_addon_scheiber/compare/v6.10.3...v6.10.4
[6.10.3]: https://github.com/eburi/ha_addon_scheiber/compare/v6.10.2...v6.10.3
[6.10.2]: https://github.com/eburi/ha_addon_scheiber/compare/v6.10.1...v6.10.2
[6.10.1]: https://github.com/eburi/ha_addon_scheiber/compare/v6.10.0...v6.10.1
[6.10.0]: https://github.com/eburi/ha_addon_scheiber/compare/v6.9.8...v6.10.0
[6.9.8]: https://github.com/eburi/ha_addon_scheiber/compare/v6.9.7...v6.9.8
[6.9.7]: https://github.com/eburi/ha_addon_scheiber/compare/v6.9.6...v6.9.7
[6.9.6]: https://github.com/eburi/ha_addon_scheiber/compare/v6.9.5...v6.9.6
[6.9.5]: https://github.com/eburi/ha_addon_scheiber/compare/v6.9.4...v6.9.5
[6.9.4]: https://github.com/eburi/ha_addon_scheiber/compare/v6.9.3...v6.9.4
[6.9.3]: https://github.com/eburi/ha_addon_scheiber/compare/v6.9.2...v6.9.3
[6.9.2]: https://github.com/eburi/ha_addon_scheiber/compare/v6.9.1...v6.9.2
[6.9.1]: https://github.com/eburi/ha_addon_scheiber/compare/v6.9.0...v6.9.1
[6.9.0]: https://github.com/eburi/ha_addon_scheiber/compare/v6.8.1...v6.9.0
[6.8.1]: https://github.com/eburi/ha_addon_scheiber/compare/v6.8.0...v6.8.1
[6.8.0]: https://github.com/eburi/ha_addon_scheiber/compare/v6.7.2...v6.8.0
[6.7.2]: https://github.com/eburi/ha_addon_scheiber/compare/v6.7.1...v6.7.2
[6.7.1]: https://github.com/eburi/ha_addon_scheiber/compare/v6.7.0...v6.7.1
[6.7.0]: https://github.com/eburi/ha_addon_scheiber/compare/v6.6.3...v6.7.0
[6.6.3]: https://github.com/eburi/ha_addon_scheiber/compare/v6.6.2...v6.6.3
[6.6.2]: https://github.com/eburi/ha_addon_scheiber/compare/v6.6.1...v6.6.2
[6.6.1]: https://github.com/eburi/ha_addon_scheiber/compare/v6.6.0...v6.6.1
[6.6.0]: https://github.com/eburi/ha_addon_scheiber/compare/v6.5.0...v6.6.0
[6.5.0]: https://github.com/eburi/ha_addon_scheiber/compare/v6.4.5...v6.5.0
[6.4.0]: https://github.com/eburi/ha_addon_scheiber/compare/v6.3.6...v6.4.0
[6.2.16]: https://github.com/eburi/ha_addon_scheiber/compare/v6.2.15...v6.2.16
[6.2.15]: https://github.com/eburi/ha_addon_scheiber/compare/v6.2.14...v6.2.15
[6.2.14]: https://github.com/eburi/ha_addon_scheiber/compare/v6.2.13...v6.2.14
[6.2.13]: https://github.com/eburi/ha_addon_scheiber/compare/v6.2.12...v6.2.13
[6.2.12]: https://github.com/eburi/ha_addon_scheiber/compare/v6.2.11...v6.2.12
[5.7.5]: https://github.com/eburi/ha_addon_scheiber/compare/v5.7.4...v5.7.5
[5.7.4]: https://github.com/eburi/ha_addon_scheiber/compare/v5.7.3...v5.7.4
[5.7.3]: https://github.com/eburi/ha_addon_scheiber/compare/v5.7.2...v5.7.3
[5.7.2]: https://github.com/eburi/ha_addon_scheiber/compare/v5.7.1...v5.7.2
[5.7.1]: https://github.com/eburi/ha_addon_scheiber/compare/v5.7.0...v5.7.1
[5.7.0]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.6...v5.7.0
[5.3.6]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.5...v5.3.6
[5.3.5]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.4...v5.3.5
[5.3.4]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.3...v5.3.4
[5.3.3]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.2...v5.3.3
[5.3.2]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.1...v5.3.2
[5.3.1]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.0...v5.3.1
[5.3.0]: https://github.com/eburi/ha_addon_scheiber/compare/v5.2.0...v5.3.0
[5.2.0]: https://github.com/eburi/ha_addon_scheiber/compare/v5.1.0...v5.2.0
[5.1.0]: https://github.com/eburi/ha_addon_scheiber/releases/tag/v5.1.0
