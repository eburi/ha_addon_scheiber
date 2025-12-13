# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/eburi/ha_addon_scheiber/compare/v5.7.5...HEAD
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
