# Archive - V5 Legacy Code

This directory contains the original v5 architecture code that serves as a **temporary fallback option** until v6.0.0 is fully validated in production.

## Contents

- `mqtt_bridge.py` - Main MQTT bridge entry point (v5.7.8)
- `devices.py` - MQTT/Home Assistant bridge layer
- `can_decoder.py` - CAN message decoding utilities
- `device_types.yaml` - Device type configuration and property extraction templates
- `scheiber.py` - Low-level CAN command functions (deprecated)

## Running Legacy Code (Temporary Fallback)

To run the v5 legacy code instead of the default v6 architecture:

1. Set `run_dev_version: true` in your Home Assistant addon configuration
2. The addon will use `archive/mqtt_bridge.py` instead of the default `can-mqtt-bridge`

**Note**: This fallback option is temporary and will be removed once v6 is fully validated in production.

## Why V6?

Version 6.0.0 introduces a new modular architecture designed to:
- **Enable future progress**: Cleaner architecture makes it easier to add support for new Scheiber devices
- **Improve maintainability**: Clear separation of hardware protocol (CAN) from MQTT integration
- **Better testability**: Comprehensive test coverage ensures reliability
- **Easier collaboration**: Well-organized code is easier to understand and modify

### Architecture Benefits

**V6 Structure**:
- Hardware layer: `scheiber/src/scheiber/` - Pure CAN protocol implementation
- MQTT layer: `scheiber/src/can_mqtt_bridge/` - Home Assistant integration
- Observer pattern: Clean state change propagation
- Comprehensive tests: 100+ tests ensure correctness

**V5 Issues** (now archived):
- Mixed concerns: Hardware and MQTT code intertwined
- Hard to extend: Adding new devices required modifying multiple layers
- Limited test coverage: Difficult to validate changes
- Complex dependencies: Changes in one area affected unrelated code

## Migration Notes

The v6 architecture is functionally equivalent to v5.7.8 but with better organization:
- All bug fixes from v5.7.8 (8-byte message parsing, heartbeat handling) are included
- Device configuration moved to cleaner YAML-based system initialization
- Easing functions integrated into scheiber module
- New features: Effect storage for Home Assistant effect selection

## Future Plans

Once v6 is validated:
- This fallback option will be removed
- Archive will remain for reference and understanding codebase evolution
- New device support will only be added to v6 architecture
