# Home Assistant Add-on: Scheiber CAN-MQTT Bridge

**Version 2.0.4** — Production-ready bridge with optimistic updates, heartbeat-based availability, and brightness control.

## Overview

This Home Assistant add-on provides a bridge between Scheiber devices on a CAN bus and MQTT, enabling seamless integration with Home Assistant through MQTT Discovery. It monitors CAN traffic, decodes device messages, publishes state updates to MQTT, and handles commands from Home Assistant with optimistic feedback for responsive UI.

### Key Features

- **CAN Bus Monitoring**: Listens to SocketCAN interface and decodes Scheiber device messages in real-time
- **MQTT Integration**: Full bidirectional communication with Home Assistant via MQTT Discovery
- **Optimistic Updates**: Immediate feedback to Home Assistant for responsive UI without waiting for device confirmation
- **Heartbeat-based Availability**: Devices automatically marked online/offline based on CAN message activity (60s timeout)
- **Brightness Control**: Full dimming support with Home Assistant-native brightness slider (0-255 levels)
- **State Persistence**: Device states saved to disk and restored on restart
- **Device Type System**: Extensible YAML-based configuration for different device types (currently supports Bloc9)
- **Retained Message Handling**: Automatic cleanup of old retained MQTT commands (5-minute age limit)
- **Bus Statistics**: Real-time monitoring of CAN bus load, message rates, and sender activity
- **Configurable Logging**: Support for debug/info/warning/error log levels

## Supported Devices

### Bloc9

Scheiber Bloc9 switch panels with up to 6 switches (S1-S6). Each switch is exposed as a fully dimmable light in Home Assistant.

**Features:**
- ON/OFF control
- 254 brightness levels (1-254, plus 0=OFF and 255=full ON)
- Optimistic state updates for instant UI feedback
- Automatic availability detection via heartbeat
- State persistence across restarts

**CAN Protocol:**
- Command ID: `0x02360600 | ((bloc9_id << 3) | 0x80)`
- Command payload: `[switch_nr, state_byte, 0x00, brightness_byte]`
  - `switch_nr`: 0-5 for S1-S6
  - `state_byte`: `0x00` (OFF), `0x01` (ON), `0x11` (dimming)
  - `brightness_byte`: 0-255 when `state_byte=0x11`
- Status prefixes: `0x00000600`, `0x02160600`, `0x02180600`, `0x021A0600`
- Status messages include switch states and current brightness levels

## MQTT Topic Structure

**Topic Prefix:** Configurable via `mqtt_topic_prefix` option (default: `homeassistant`)

### Bus Statistics
```
<prefix>/scheiber
```
JSON payload with:
- `bus_load`: Messages per second
- `messages_per_minute`: Message count in last 60 seconds
- `total_messages`: Cumulative message count since start
- `unique_sender_ids`: Count of unique CAN sender IDs seen
- `known_sender_ids`: Count of recognized device types
- `unique_sender_id_list`: Array of all sender IDs
- `known_sender_id_list`: Array of recognized sender IDs

### Device Info
```
<prefix>/scheiber/<device-type>/<bus-id>
```
JSON payload with device metadata and current switch states:
```json
{
  "name": "Bloc9",
  "device_type": "bloc9",
  "bus_id": 7,
  "switches": {
    "s1": "1",
    "s2": "0",
    "s3": "1"
  }
}
```

### Device State Topics
```
<prefix>/scheiber/<device-type>/<bus-id>/<property>/state
<prefix>/scheiber/<device-type>/<bus-id>/<property>/brightness
<prefix>/scheiber/<device-type>/<bus-id>/<property>/availability
```
Example: 
- `homeassistant/scheiber/bloc9/7/s5/state` → `1` (ON) or `0` (OFF)
- `homeassistant/scheiber/bloc9/7/s5/brightness` → `0-255` (raw brightness value)
- `homeassistant/scheiber/bloc9/7/s5/availability` → `online` or `offline`

**Note:** Brightness value 0 means OFF, 255 means full ON without dimming control, 1-254 are actual dimming levels.

### Device Command Topics
```
<prefix>/scheiber/<device-type>/<bus-id>/<property>/set
<prefix>/scheiber/<device-type>/<bus-id>/<property>/set_brightness
```
Example: 
- `homeassistant/scheiber/bloc9/7/s5/set` → `1` (ON) or `0` (OFF)
- `homeassistant/scheiber/bloc9/7/s5/set_brightness` → `0-255` (brightness level)

Publish to these topics to control devices. The bridge:
1. Sends the CAN command immediately
2. Publishes optimistic state update to MQTT (instant HA feedback)
3. Clears any retained command messages
4. Updates internal state cache and persists to disk

**Supported payloads:**
- ON/OFF: `1`, `ON`, `on`, `true`, `True` / `0`, `OFF`, `off`, `false`, `False`
- Brightness: `0-255` (0 = OFF, 1-254 = dimming levels, 255 = full ON)
- Empty payloads are silently ignored (used for clearing retained messages)

**Home Assistant Integration:**
- Uses `on_command_type: "brightness"` to prevent duplicate ON commands after brightness changes
- Optimistic mode disabled - state updates come from MQTT feedback
- Availability tied to device heartbeat (60-second timeout)

### Discovery Configuration
```
<prefix>/scheiber/<device-type>/<bus-id>/<property>/config
```
Example: `homeassistant/scheiber/bloc9/7/s5/config`

Published once per property on startup. Configures Home Assistant entities with:
- Unique ID (includes `_v2` suffix for config update recognition)
- Device information (identifiers, name, model, manufacturer)
- Command and state topics
- Availability topic with online/offline payloads
- Brightness configuration with supported color modes
- QoS and retain settings

See:
- [Home Assistant MQTT Light](https://www.home-assistant.io/integrations/light.mqtt/)
- [Home Assistant MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)

## Configuration

### Add-on Options

```yaml
can_interface: "can1"         # SocketCAN interface name (default: can1)
mqtt_host: "localhost"        # MQTT broker hostname
mqtt_port: 1883               # MQTT broker port
mqtt_user: "mqtt_user"        # MQTT username
mqtt_password: "mqtt"         # MQTT password
mqtt_topic_prefix: "homeassistant"  # MQTT topic prefix (important for HA discovery)
log_level: "info"             # Logging level: debug/info/warning/error
data_dir: "/data"             # Directory for persistent state storage
```

**Important Notes:**
- `mqtt_topic_prefix` should be `homeassistant` for automatic Home Assistant discovery
- `data_dir` is where device states are persisted (typically `/data` in Docker/HA)
- State cache files stored at `{data_dir}/state_cache/bloc9_{device_id}.json`

### Device Configuration

Device types are defined in `scheiber/src/device_types.yaml`. This YAML file controls:
- Device type recognition from CAN arbitration IDs
- Bus ID extraction formulas
- Message matchers (address/mask patterns)
- Property extraction templates

Example structure:
```yaml
bloc9:
  name: "Bloc9"
  bus_id_extractor:
    type: "formula"
    formula: "((arb_id & 0xFF) & ~0x80) >> 3"
  matchers:
    - address: 0x00000600
      mask: 0xFFFFFF00
      name: "Status update"
      properties:
        stat1_0: {template: "(1,0)"}  # Bit-level extraction
        # ... more status bits
    
    - address: 0x02160600
      mask: 0xFFFFFF00
      name: "S1 & S2 Status update"
      properties:
        s1: {template: "(3,0)", formatter: "{}"}  # Switch 1 state
        s1_brightness: {template: "[0]", formatter: "{}"}  # Switch 1 brightness byte
        s2: {template: "(7,0)", formatter: "{}"}  # Switch 2 state  
        s2_brightness: {template: "[4]", formatter: "{}"}  # Switch 2 brightness byte
    
    - address: 0x02180600
      mask: 0xFFFFFF00
      name: "S3 & S4 Status update"
      properties:
        s3: {template: "(3,0)"}
        s3_brightness: {template: "[0]"}
        s4: {template: "(7,0)"}
        s4_brightness: {template: "[4]"}
    
    - address: 0x021A0600
      mask: 0xFFFFFF00
      name: "S5 & S6 Status update"
      properties:
        s5: {template: "(3,0)"}
        s5_brightness: {template: "[0]"}
        s6: {template: "(7,0)"}
        s6_brightness: {template: "[4]"}
```

**Property Template Syntax:**
- `"(byte_index,bit_index)"` - Extract single bit (returns 0 or 1)
- `"[byte_index]"` - Extract full byte (returns 0-255)

**Naming Conventions:**
- Properties starting with `stat` are used only for heartbeat tracking (not published)
- Properties ending with `_brightness` are automatically linked to their base property
- Base properties (e.g., `s1`, `s2`) become light entities in Home Assistant

## Architecture

### Core Components

**Production Code (`scheiber/src/`):**
- **`mqtt_bridge.py`**: Main bridge application
  - CAN message listener loop
  - MQTT client management with reconnection handling
  - Device instance tracking and lifecycle management
  - Command routing from MQTT to device handlers
  - Retained message age checking (5-minute threshold)
  - Heartbeat checking for all devices (every 10 messages)
  - Bus statistics collection and publishing

- **`devices.py`**: Device class hierarchy
  - `ScheiberCanDevice`: Abstract base class with common MQTT/CAN functionality
  - `Bloc9`: Concrete implementation for Bloc9 switch panels
    - Heartbeat-based availability tracking (60-second timeout)
    - Optimistic state publishing for responsive UI
    - Command handling with CAN message generation
    - State persistence to JSON files
    - Discovery configuration publishing

- **`can_decoder.py`**: CAN message decoding utilities
  - `find_device_and_matcher()`: Identifies device type from arbitration ID
  - `extract_property_value()`: Extracts property values using templates
  - Bit-level and byte-level extraction support

- **`device_types.yaml`**: Device configuration database
  - YAML-based device type definitions
  - Bus ID extraction formulas
  - Message matchers with address/mask patterns
  - Property templates for value extraction

- **`scheiber.py`**: Low-level CAN command functions
  - `bloc9_switch()`: Send switch command to Bloc9 device
  - `send_burst()`: Send command burst (press/release sequence)

- **`requirements.txt`**: Python dependencies
  - `python-can==4.3.1` - CAN bus interface
  - `paho-mqtt==2.1.0` - MQTT client
  - `PyYAML==6.0.1` - YAML configuration parsing

**Debug Tools (`scheiber/src/tools/`):**
- **`canlistener.py`**: Real-time CAN sniffer with decoded output
- **`analyser.py`**: Interactive CAN analyzer (spacebar to clear screen)
- **`analyze_dimming.py`**: Tool for analyzing dimming byte patterns
- **`light.py`**: Helper for sending light button press sequences
- **`can_names.csv`**: Human-readable mapping of known arbitration IDs
- **`data/`**: Sample CAN dumps and protocol documentation

**Deployment:**
- **`config.yaml`**: Home Assistant add-on configuration
- **`Dockerfile`**: Container build with Alpine Linux base
- **`run.sh`**: Entry point script (activates virtualenv, starts bridge)

### Class Hierarchy

```
ScheiberCanDevice (Abstract Base Class)
├── Device lifecycle management
├── MQTT topic generation
├── State tracking and persistence helpers
├── Default no-op heartbeat methods
└── Abstract methods: publish_discovery_config(), publish_state()

    └── Bloc9 (Concrete Implementation)
        ├── Heartbeat tracking (60s timeout)
        ├── Online/offline state management
        ├── Command handling (ON/OFF, brightness)
        ├── Optimistic state publishing
        ├── CAN message construction
        ├── State persistence to JSON
        └── Discovery config with brightness support
```

### Data Flow

**CAN → MQTT (State Updates):**
1. CAN message received on SocketCAN interface
2. `find_device_and_matcher()` identifies device type and bus ID
3. Device instance created (or retrieved if exists)
4. `update_heartbeat()` called to mark device online
5. Properties extracted from CAN payload using templates
6. `publish_state()` publishes each property to MQTT
7. State persisted to JSON file

**MQTT → CAN (Commands):**
1. MQTT command received on `/set` or `/set_brightness` topic
2. Topic routed to device's `handle_command()` method
3. Command parsed and validated
4. CAN message constructed with proper arbitration ID and payload
5. CAN message sent via `can_bus.send()`
6. Optimistic state published to MQTT immediately
7. Internal state updated and persisted
8. Retained command message cleared (if was retained)

**Heartbeat System:**
- Every CAN message match updates device's `last_heartbeat` timestamp
- Every 10 CAN messages, all devices check their heartbeat
- If >60s since last heartbeat: device marked offline, all properties unavailable
- When new message arrives after offline: device marked online, all properties available
- Availability state published to individual property availability topics

### State Persistence

Device states are saved to: `{data_dir}/state_cache/bloc9_{device_id}.json`

Example state file:
```json
{
  "s1": "1",
  "s1_brightness": 150,
  "s2": "0",
  "s3": "1",
  "s3_brightness": 200
}
```

States are:
- Loaded on device initialization
- Published to MQTT as initial state
- Updated on every command and CAN message
- Persisted after every state change

### Python Environment

- **Runtime**: Python 3.11+ (tested with 3.13)
- **Virtualenv**: `scheiber/src/.venv` (created in Docker build)
- **Working Directory**: 
  - Production code: `scheiber/src/`
  - Debug tools: `scheiber/src/tools/` (adds parent to `sys.path`)
- **Dependencies**: Installed from `scheiber/src/requirements.txt`

### Docker Container

- **Base**: Alpine Linux (minimal footprint)
- **Build Process**:
  1. Install system packages (python3, py3-pip, gcc, etc.)
  2. Create virtualenv at `/src/.venv`
  3. Install Python dependencies
  4. Copy source files
- **Runtime**: `run.sh` activates virtualenv and starts `mqtt_bridge.py`
- **Networking**: Host network mode for CAN interface access
- **Privileges**: `NET_ADMIN`, `SYS_RAWIO` for CAN bus access

## Development

### Running Locally

**Production Code** (run from `scheiber/src/`):

```bash
cd scheiber/src

# Activate virtualenv
source .venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt

# Run MQTT bridge with debug logging
python mqtt_bridge.py --can-interface can1 \
                      --mqtt-host localhost \
                      --mqtt-port 1883 \
                      --mqtt-user mqtt_user \
                      --mqtt-password mqtt \
                      --mqtt-topic-prefix homeassistant \
                      --log-level debug \
                      --data-dir /tmp/test_data

# Send test switch command (bloc9_id=7, switch_nr=5)
python scheiber.py 7 5
```

**Debug Tools** (run from `scheiber/src/tools/`):

```bash
cd scheiber/src/tools

# CAN listener with decoded output
python canlistener.py can1

# Interactive analyzer (spacebar to clear)
python analyser.py -i can1

# Light button press helper
python light.py can1

# Analyze dimming patterns
python analyze_dimming.py can1
```

### Command-Line Options

**mqtt_bridge.py:**
```
--can-interface     CAN interface name (default: can1)
--mqtt-host         MQTT broker hostname (default: localhost)
--mqtt-port         MQTT broker port (default: 1883)
--mqtt-user         MQTT username (default: mqtt_user)
--mqtt-password     MQTT password (default: mqtt)
--mqtt-topic-prefix MQTT topic prefix (default: homeassistant)
--log-level         Logging level: debug/info/warning/error (default: info)
--data-dir          Directory for persistent data (default: .state_cache in src)
```

### Adding New Device Types

1. **Analyze CAN Traffic**
   - Use `canlistener.py` or `analyser.py` to capture messages
   - Identify arbitration ID patterns
   - Save sample dumps to `scheiber/src/tools/data/` for reference

2. **Define Bus ID Extraction**
   - Determine how device ID is encoded in arbitration ID
   - Write formula (e.g., `((arb_id & 0xFF) & ~0x80) >> 3`)
   - Test with known device IDs

3. **Create Matchers**
   - Identify unique message types (address/mask pairs)
   - Define meaningful names for each matcher
   - Group related properties under each matcher

4. **Define Property Templates**
   - Use `"(byte_index,bit_index)"` for bit extraction
   - Use `"[byte_index]"` for byte extraction
   - Follow naming conventions:
     - `stat*` = internal status (heartbeat only)
     - `*_brightness` = brightness values
     - Base names = switch states

5. **Update device_types.yaml**
   ```yaml
   new_device:
     name: "Device Name"
     bus_id_extractor:
       type: "formula"
       formula: "your_extraction_formula"
     matchers:
       - address: 0xYYYYYYYY
         mask: 0xFFFFFF00
         name: "Matcher Description"
         properties:
           property1: {template: "(0,0)"}
           property2: {template: "[1]"}
   ```

6. **Create Device Class**
   - Add new class in `devices.py` inheriting from `ScheiberCanDevice`
   - Implement `publish_discovery_config()` for Home Assistant
   - Implement `publish_state()` for state updates
   - Implement `handle_command()` for command handling (if bidirectional)
   - Add to `DEVICE_TYPE_CLASSES` registry

7. **Test**
   - Run mqtt_bridge with debug logging
   - Verify device detection and property extraction
   - Test commands if device supports them
   - Check Home Assistant entity creation

### Version Management

After making code changes, update `version` in `scheiber/config.yaml` following semantic versioning:

- **PATCH** (X.Y.Z): Bug fixes, small tweaks, no API changes
  - Example: Empty payload handling, log message fixes
  - Increment: `2.0.3` → `2.0.4`

- **MINOR** (X.Y.0): New features, backward-compatible changes
  - Example: New command parameters with defaults, new optional functionality
  - Increment: `2.0.4` → `2.1.0`

- **MAJOR** (X.0.0): Breaking changes, API changes, changed behavior
  - Example: MQTT topic structure changes, removed functionality
  - Increment: `2.0.4` → `3.0.0`

### Testing

**No Automated Tests**: This project lacks automated tests due to hardware dependency. Testing approach:

1. **Manual Hardware Testing**
   - Test with actual Bloc9 devices on CAN bus
   - Verify commands via physical switch panel feedback
   - Monitor CAN bus with `candump can1`

2. **MQTT Verification**
   - Subscribe to all topics: `mosquitto_sub -v -t 'homeassistant/scheiber/#'`
   - Verify state updates appear correctly
   - Test commands: `mosquitto_pub -t 'homeassistant/scheiber/bloc9/7/s5/set' -m '1'`

3. **Home Assistant Integration**
   - Check auto-discovery creates entities
   - Verify controls work in HA UI
   - Test brightness slider responsiveness
   - Confirm availability updates correctly

4. **Log Analysis**
   - Enable debug logging
   - Check for errors or warnings
   - Verify heartbeat updates
   - Monitor retained message handling

## Troubleshooting

### Common Issues

**"Invalid command payload: - invalid literal for int()" Error**
- **Cause**: Empty retained MQTT messages left from previous runs
- **Solution**: The bridge now handles this automatically (v2.0.4+). Empty payloads are detected early and logged but don't cause errors.
- **Prevention**: Bridge clears retained command messages after execution

**Devices Not Recovering After Timeout**
- **Cause**: Heartbeat updates not triggered on all message types
- **Solution**: Fixed in v2.0.2 - heartbeat updates on ANY matching CAN message
- **Check**: Verify CAN bus traffic with `candump can1`

**Brightness Changes Followed by Full Brightness**
- **Cause**: Home Assistant sending ON command after brightness
- **Solution**: Fixed in v2.0.1 with `on_command_type: "brightness"`
- **Verify**: Check discovery config includes correct on_command_type

**Lights Unavailable in Home Assistant UI**
- **Cause**: Old per-property availability system
- **Solution**: v2.0.0+ uses heartbeat-based availability (60s timeout)
- **Check**: Look for status messages (0x00000600 prefix) in CAN traffic

**Spinning Loading Indicator After Brightness Change**
- **Cause**: Waiting for state confirmation from bridge
- **Solution**: v2.0.3+ implements optimistic state updates
- **Verify**: State should update immediately in HA, not after CAN confirmation

**Old Configs Not Updating in Home Assistant**
- **Cause**: unique_id not changed, HA won't reload config
- **Solution**: v1.6.0+ uses unique_id with "_v2" suffix
- **Manual Fix**: Delete old entities in HA, restart bridge

**Commands Execute on Bridge Startup**
- **Cause**: Retained MQTT commands from previous session
- **Solution**: v1.8.0+ checks message age (300s max) and clears after execution
- **Prevention**: Bridge automatically clears retained messages

### Debugging Commands

**Check CAN Bus Traffic:**
```bash
# Show all CAN messages
candump can1

# Show only specific arbitration IDs
candump can1,023:7FF  # Bloc9 commands

# Log to file for analysis
candump -l can1
```

**MQTT Debugging:**
```bash
# Subscribe to all scheiber topics
mosquitto_sub -v -t 'homeassistant/scheiber/#'

# Subscribe to specific device
mosquitto_sub -v -t 'homeassistant/scheiber/bloc9/7/#'

# Check discovery configs
mosquitto_sub -v -t 'homeassistant/scheiber/+/+/+/config'

# Test manual command
mosquitto_pub -t 'homeassistant/scheiber/bloc9/7/s5/set' -m '1'
mosquitto_pub -t 'homeassistant/scheiber/bloc9/7/s5/set_brightness' -m '128'

# Clear all retained messages
mosquitto_pub -t 'homeassistant/scheiber/bloc9/7/s5/set' -n -r
```

**Check Bridge Logs:**
```bash
# In Home Assistant Supervisor
# Go to Add-ons → Scheiber MQTT Bridge → Log

# Or if running locally:
python mqtt_bridge.py --log-level debug
```

**Verify Python Environment:**
```bash
cd scheiber/src
source .venv/bin/activate
python -c "import can, paho.mqtt.client, yaml; print('Dependencies OK')"
```

### Log Interpretation

**Normal Operation:**
```
INFO - Bloc9 device bus_id=7 matched message with ID 0x023606D0
DEBUG - Extracted properties: {'s5': 1, 's5_brightness': 200}
INFO - Published state to homeassistant/scheiber/bloc9/7/s5/state: ON
DEBUG - Updated heartbeat for Bloc9 bus_id=7
```

**Device Going Offline:**
```
WARNING - Bloc9 device bus_id=7 offline (no heartbeat for 60s)
DEBUG - Published availability offline for all properties
```

**Device Recovery:**
```
INFO - Bloc9 device bus_id=7 coming back online
DEBUG - Published availability online for all properties
```

**Retained Message Handling:**
```
INFO - Received command for Bloc9 bus_id=7 s5: 1 (retained, age: 15.3s)
INFO - Command successful, clearing retained message
```

**Empty Payload Detection:**
```
DEBUG - Empty payload received, ignoring command
```

### Basic Troubleshooting

**No MQTT Messages**
- Check MQTT broker connection and credentials
- Verify CAN interface is up: `ip link show can1`
- Enable debug logging: `log_level: "debug"`

**Device Not Discovered**
- Ensure device is sending CAN messages
- Check if device type is defined in `device_types.yaml`
- Verify matcher address/mask patterns
- Review logs for unmatched message IDs

**Import Errors**
- Ensure virtualenv is activated
- Reinstall dependencies: `pip install -r requirements.txt`
- Check Python version: `python --version` (should be 3.11+)

### Getting Help

When reporting issues, include:
1. Bridge version (from `scheiber/config.yaml`)
2. Full error message and stack trace
3. Relevant log output (with `--log-level debug`)
4. CAN dump showing message patterns (`candump -l can1`)
5. MQTT messages (`mosquitto_sub -v -t 'homeassistant/scheiber/#'`)
6. Home Assistant version and MQTT broker version

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