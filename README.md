# Home Assistant Add-on: Scheiber CAN-MQTT Bridge

**⚠️ EXPERIMENTAL — This add-on is under active development and may change significantly. Use at your own risk.**

## Overview

This Home Assistant add-on provides a bridge between Scheiber devices on a CAN bus and MQTT, enabling integration with Home Assistant through MQTT Discovery. It monitors CAN traffic, decodes device messages, and publishes state updates to MQTT topics that Home Assistant can automatically discover and configure.

### Key Features

- **CAN Bus Monitoring**: Listens to SocketCAN interface and decodes Scheiber device messages
- **MQTT Integration**: Publishes device states to MQTT broker with Home Assistant Auto Discovery support
- **Device Type System**: Extensible YAML-based configuration for different device types (currently supports Bloc9)
- **Property Extraction**: Template-based extraction of device properties from CAN message payloads
- **Bus Statistics**: Real-time monitoring of CAN bus load, message rates, and sender activity
- **Configurable Logging**: Support for debug/info/warning/error log levels

## Supported Devices

### Bloc9

Scheiber Bloc9 switch panels with up to 6 switches. Each switch is exposed as a dimmable light in Home Assistant.

**CAN Protocol:**
- Command ID: `0x02360600 | ((bloc9_id << 3) | 0x80)`
- Status prefixes: `0x00000600`, `0x02160600`, `0x02180600`, `0x021A0600`
- Switch states: S1-S6 (ON/OFF, dimming support in progress)

## MQTT Topic Structure

### Bus Statistics
```
<prefix>/scheiber
```
JSON payload with:
- `load`: Messages per minute (last 60 seconds)
- `message_rate`: Average rate over sliding window
- `unique_senders`: Count of unique CAN sender IDs
- `known_senders`: Count of recognized device types
- `sender_ids`: List of all sender IDs
- `known_sender_ids`: List of recognized sender IDs

### Device State
```
<prefix>/scheiber/<device-type>/<bus-id>/<property>/state
```
Example: `homeassistant/scheiber/bloc9/10/s1/state` → `1` (ON) or `0` (OFF)

### Home Assistant MQTT Discovery - Device Configuration
```
<prefix>/scheiber/<device-type>/<bus-id>/<property>/config
```
Example: `homeassistant/scheiber/bloc9/10/s2/config`

Automatically configures light entities in Home Assistant with:
- Unique ID
- Device information
- Command and state topics
- Availability topic

See:
- [Home Assistant MQTT Light](https://www.home-assistant.io/integrations/light.mqtt/)
- [Home Assistant MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)

## Configuration

### Add-on Options

```yaml
mqtt_host: "localhost"        # MQTT broker hostname
mqtt_port: 1883               # MQTT broker port
mqtt_username: ""             # MQTT username (optional)
mqtt_password: ""             # MQTT password (optional)
mqtt_topic_prefix: "homeassistant"  # MQTT topic prefix
can_interface: "can0"         # SocketCAN interface name
log_level: "info"             # Logging level: debug/info/warning/error
```

### Device Configuration

Device types are defined in `scheiber/tools/device_types.yaml`. To add new device types or modify existing ones, edit this YAML configuration file.

Example structure:
```yaml
bloc9:
  name: "Scheiber Bloc9"
  bus_id_extractor:
    type: "formula"
    value: "((arb_id & 0xFF) & ~0x80) >> 3"
  matchers:
    - address: 0x00000600
      mask: 0xFFFFFF00
      properties:
        s1: {template: "(0,0)", format: "{}", description: "Switch 1"}
        s2: {template: "(0,1)", format: "{}", description: "Switch 2"}
        # ... more switches
```

## Architecture

### Core Components

- **`mqtt_bridge.py`**: Main bridge application that connects CAN listener to MQTT publisher
- **`canlistener.py`**: CAN message decoder with device type matching and property extraction
- **`device_types.yaml`**: External configuration for device definitions
- **`scheiber.py`**: Low-level CAN utilities (`bloc9_switch()`, `send_burst()`, `test_switch()`)
- **`light.py`**: Helper for sending light button press sequences
- **`analyze_dimming.py`**: Analysis tool for identifying dimming byte patterns

### Python Environment

- Python 3.13 with virtualenv at `/tools/.venv`
- Dependencies: `python-can==4.3.1`, `paho-mqtt==2.1.0`, `PyYAML==6.0.1`
- All scripts run from the `scheiber/tools/` working directory

### Docker Container

- Alpine Linux base
- Pre-built virtualenv with all dependencies
- Entry point: `run.sh` activates virtualenv and starts `mqtt_bridge.py`

## Development

### Running Locally

All commands should be run from the `scheiber/tools/` directory:

```bash
cd scheiber/tools

# Activate virtualenv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run CAN listener
python canlistener.py can0

# Run MQTT bridge
python mqtt_bridge.py --mqtt-host localhost --mqtt-port 1883 --log-level debug

# Test switch command
python scheiber.py 3 7  # bloc9_id=3, switch_nr=7

# Interactive analyzer (spacebar to clear)
python analyser.py -i can0

# Analyze dimming patterns
python analyze_dimming.py can0
```

### Adding New Device Types

1. Analyze CAN messages to identify patterns
2. Update `scheiber/tools/device_types.yaml` with new device definition
3. Define matchers (address/mask pairs) for message types
4. Add property templates for extracting values from payloads
5. Test with real hardware or dump files in `scheiber/tools/data/`

### Version Management

After code changes, update `version` in `scheiber/config.yaml` following semantic versioning:
- **PATCH** (0.0.X): Bug fixes, no API changes
- **MINOR** (0.X.0): New features, backward-compatible
- **MAJOR** (X.0.0): Breaking changes

## Troubleshooting

### No MQTT Messages
- Check MQTT broker connection and credentials
- Verify CAN interface is up: `ip link show can0`
- Enable debug logging: `log_level: "debug"`

### Device Not Discovered
- Ensure device is sending CAN messages
- Check if device type is defined in `device_types.yaml`
- Verify matcher address/mask patterns
- Review logs for unmatched message IDs

### Import Errors
- Ensure virtualenv is activated
- Reinstall dependencies: `pip install -r requirements.txt`
- Check Python version: `python --version` (should be 3.13+)

## Known Limitations

- Dimming protocol not yet fully decoded (infrastructure ready, byte patterns unknown)
- Only Bloc9 devices currently supported
- Requires SocketCAN interface (Linux only)
- No automated tests (hardware-dependent)

## References

- [python-can documentation](https://python-can.readthedocs.io/)
- [Paho MQTT Python](https://eclipse.dev/paho/index.php?page=clients/python/index.php)
- [Home Assistant MQTT Integration](https://www.home-assistant.io/integrations/mqtt/)
- Sample CAN dumps in `scheiber/tools/data/`
- Device mapping in `scheiber/tools/can_names.csv`

## License

See repository license file.

## Contributing

This is an experimental project. Contributions welcome, but expect significant changes as the protocol is reverse-engineered.