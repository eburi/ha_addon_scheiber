# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
