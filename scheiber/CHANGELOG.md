# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.6...HEAD
[5.3.6]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.5...v5.3.6
[5.3.5]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.4...v5.3.5
[5.3.4]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.3...v5.3.4
[5.3.3]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.2...v5.3.3
[5.3.2]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.1...v5.3.2
[5.3.1]: https://github.com/eburi/ha_addon_scheiber/compare/v5.3.0...v5.3.1
[5.3.0]: https://github.com/eburi/ha_addon_scheiber/compare/v5.2.0...v5.3.0
[5.2.0]: https://github.com/eburi/ha_addon_scheiber/compare/v5.1.0...v5.2.0
[5.1.0]: https://github.com/eburi/ha_addon_scheiber/releases/tag/v5.1.0
