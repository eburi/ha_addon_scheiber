# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
