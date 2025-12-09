# Home Assistant Add-on: Scheiber CAN-MQTT Bridge

Experimental bridge for Scheiber CAN devices with MQTT integration.

⚠️ **EXPERIMENTAL**: This is an ongoing reverse-engineering project. The Scheiber CAN protocol is not fully documented, and functionality may be incomplete or change significantly.

## Overview

This Home Assistant add-on provides a bridge between Scheiber devices on a CAN bus and MQTT, enabling integration with Home Assistant through MQTT Discovery. It monitors CAN traffic, decodes device messages, and publishes state updates to MQTT.

**Explicit entity configuration for safety and control:** You must define which outputs to expose via a `scheiber.yaml` configuration file placed in Home Assistant's `/config/` directory.

**Device Structure (v4.0.0+):** All entities belong to a single unified "Scheiber" device:
- Single "Scheiber - Marine Lighting Control System" device in Home Assistant
- All lights and switches appear as entities under this one device
- Cleaner entity naming: `light.scheiber_<name>` instead of repetitive names
- Simplified device management with all Scheiber entities in one place

**JSON Schema (v5.0.0+):** Lights use JSON MQTT payloads for better Home Assistant integration:
- Combined state and brightness in single topic: `{"state": "ON", "brightness": 255}`
- Supports smooth transitions with easing functions (reduces MQTT traffic)
- Automatic easing selection: ease-out-cubic for fade-up, ease-in-cubic for fade-down
- Backwards compatible: v4 list-based configs still work
- New dict-based config format prevents duplicate output assignments

### Current Features

- **CAN-MQTT Bridge**: Translates CAN messages to MQTT topics
- **Bloc9 Switch Support**: ON/OFF control and brightness (0-255) for 6-switch panels
- **Explicit Entity Configuration**: Define which outputs to expose as lights or switches
- **MQTT Discovery**: Automatic Home Assistant entity creation for configured outputs
- **Heartbeat Availability**: Devices marked online/offline based on CAN traffic (60s timeout)
- **State Persistence**: Device states saved between restarts
- **Optimistic Updates**: Immediate UI feedback (may not reflect actual device state)
- **Extensible Architecture**: YAML-based device configuration for future expansion
- **Retained Message Handling**: Automatic cleanup of old MQTT commands (5-minute age limit)

## Supported Devices

### Bloc9

Scheiber Bloc9 switch panels with up to 6 switches (S1-S6). Each switch appears as a dimmable light in Home Assistant.

**Capabilities:**
- ON/OFF control
- Brightness control (0-255 range, protocol partially understood)
- Automatic online/offline detection
- State persistence

**Known CAN Protocol Details:**
- Command ID: `0x02360600 | ((bloc9_id << 3) | 0x80)`
- Status prefixes: `0x00000600`, `0x02160600`, `0x02180600`, `0x021A0600`
- Bus IDs: Typically 2-10 (extracted from arbitration ID)

⚠️ Protocol details are based on reverse-engineering and may be incomplete.

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

**v5.0.0+ (JSON Schema for Lights):**
```
<prefix>/scheiber/<device-type>/<bus-id>/<property>/state
<prefix>/scheiber/<device-type>/<bus-id>/<property>/availability
```

Lights publish JSON state:
```json
{"state": "ON", "brightness": 255}
```

Example: 
- `homeassistant/scheiber/bloc9/7/s5/state` → `{"state": "ON", "brightness": 128}` (light at 50%)
- `homeassistant/scheiber/bloc9/7/s5/state` → `{"state": "OFF", "brightness": 0}` (light off)
- `homeassistant/scheiber/bloc9/7/s5/availability` → `online` or `offline`

Non-light entities (switches) use simple payloads:
- `homeassistant/scheiber/bloc9/7/s5/state` → `ON` or `OFF`

**Note:** Brightness 0 means OFF, 255 means full ON, 1-254 are dimming levels.

### Device Command Topics

**v5.0.0+ (JSON Schema for Lights):**
```
<prefix>/scheiber/<device-type>/<bus-id>/<property>/set
```

Lights accept JSON commands:
```json
{"state": "ON", "brightness": 200, "transition": 2}
```

Example commands:
- Turn on at 50%: `{"state": "ON", "brightness": 128}`
- Turn off: `{"state": "OFF"}`
- Turn on with 2s transition: `{"state": "ON", "brightness": 255, "transition": 2}`

Non-light entities (switches) accept simple ON/OFF:
- `ON`, `1`, `true` → Turn on
- `OFF`, `0`, `false` → Turn off

**Bridge Behavior:**
1. Sends the CAN command immediately
2. Publishes optimistic state update to MQTT (instant HA feedback)
3. Clears any retained command messages
4. Updates internal state cache and persists to disk

**Transition Support:**

The bridge supports smooth brightness transitions with easing functions, reducing MQTT traffic and offloading processing from Home Assistant to the bridge itself.

**Performance:**
- Update rate: 10 Hz (100ms per frame) - smooth perceptually natural transitions
- CAN bus load: ~10 messages/second per transitioning light
- Safe capacity: Up to 6 simultaneous transitions (~60 msg/s, <6% of CAN bus capacity)
- Critical safety: All transitions cancelled immediately on new command (guaranteed OFF)
- Bloc9-friendly: Update rate respects Bloc9's internal PWM controller

**Supported Easing Functions:**
- `ease_in_out_sine` (default) - Natural looking transitions, smooth start and end
- `ease_in_sine`, `ease_out_sine` - Sine-based acceleration/deceleration
- `ease_in_out_quad`, `ease_in_quad`, `ease_out_quad` - Quadratic curves
- `ease_in_out_cubic`, `ease_in_cubic`, `ease_out_cubic` - Cubic curves (stronger)
- `ease_in_out_quart`, `ease_in_quart`, `ease_out_quart` - Quartic curves (strongest)
- `linear` - No easing, constant speed

**Automatic Easing Selection:**
The bridge intelligently selects easing based on context:
- Fading up from off (0 → brightness): Uses `ease_out_cubic` for snappy start
- Fading down to off (brightness → 0): Uses `ease_in_cubic` for gentle end
- General transitions: Uses `ease_in_out_sine` for natural appearance

**Safety Guarantees:**
- Any new command immediately cancels running transitions
- OFF commands guaranteed to stop brightness changes instantly
- No orphaned transitions from rapid commands
- Skips pointless transitions when already at target brightness

**Visual Reference:**

![Easing Functions](ease-functions.png)

*Easing curves visualization - thanks to [Ashley Bischoff](https://community.home-assistant.io/t/ashley-s-light-fader-2-0-fade-lights-and-or-color-temperature-with-your-choice-of-easing-curves-including-ease-in-ease-out-and-ease-in-out/584077) for shamelessly inspiring, learning from, and copying ideas from Ashley's Light Fader script.*

**Backwards Compatibility:**
- Legacy v4 ON/OFF commands still accepted for lights
- Automatically converted to JSON state internally

### MQTT Discovery Configuration

**Device Structure (v4.0.0+):**

All Scheiber entities belong to a single unified device in Home Assistant:

1. **Unified Scheiber Device** — Single device for all entities
   - Device identifier: `scheiber_system`
   - Device name: "Scheiber"
   - Device model: "Marine Lighting Control System"
   - All lights and switches appear as entities under this device

2. **Entity Discovery** — Standard Home Assistant pattern
   - Discovery: `<mqtt_topic_prefix>/{component}/{entity_id}/config`
   - Each entity references the unified Scheiber device
   - No `via_device` hierarchy - flat structure under one device

**Discovery Topic Pattern** (follows standard Home Assistant convention):
```
<mqtt_topic_prefix>/{component}/{object_id}/config
```

Examples:
- `homeassistant/light/scheiber_salon_working_light/config` — Light entity
- `homeassistant/switch/scheiber_salon_water_pump/config` — Switch entity

Note: Entity names now include "scheiber_" prefix for clarity when multiple devices exist

**State & Command Topics** (scheiber-specific namespace):
```
<mqtt_topic_prefix>/scheiber/<device-type>/<bus-id>/<output>/state
<mqtt_topic_prefix>/scheiber/<device-type>/<bus-id>/<output>/set
<mqtt_topic_prefix>/scheiber/<device-type>/<bus-id>/<output>/availability
```

Examples:
- `homeassistant/scheiber/bloc9/7/s1/state` — Current state
- `homeassistant/scheiber/bloc9/7/s1/set` — Command topic
- `homeassistant/scheiber/bloc9/7/s1/brightness` — Current brightness
- `homeassistant/scheiber/bloc9/7/s1/set_brightness` — Brightness command
- `homeassistant/scheiber/bloc9/7/s1/availability` — Online/offline status

**Published discovery config includes:**
- Unique ID for each entity
- Unified Scheiber device information (identifier: `scheiber_system`)
- State, command, and availability topic references
- Brightness configuration (for lights only)
- QoS and retain settings
- No `via_device` - all entities directly belong to the Scheiber device

See:
- [Home Assistant MQTT Light](https://www.home-assistant.io/integrations/light.mqtt/)
- [Home Assistant MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)

## Configuration

### Entity Configuration (`scheiber.yaml`) — **REQUIRED**

You must create a `scheiber.yaml` configuration file to expose entities via MQTT Discovery. This adds safety by preventing accidental control of critical systems.

**Location**: Place this file in Home Assistant's `/config/` directory (e.g., `/config/scheiber.yaml`)

**Purpose**: Explicitly define which Bloc9 outputs to expose to Home Assistant, their entity names, and whether they should appear as lights or switches.

#### Configuration Structure

**v5.0.0+ Dict Format (Recommended):**

```yaml
bloc9:
  - bus_id: 7
    name: "Salon Bloc9"
    lights:
      s1:  # Output as dict key prevents duplicates
        name: "Salon Working Light"
      s2:
        name: "Salon Reading Light"
        entity_id: "light.salon_reading_light"  # Optional custom ID
    switches:
      s3:
        name: "Salon Fan"
```

**v4.0.0 List Format (Still Supported):**

```yaml
bloc9:
  - bus_id: 7
    name: "Salon Bloc9"
    lights:  # Output specified in list items
      - name: "Salon Working Light"
        output: s1
      - name: "Salon Reading Light"
        entity_id: "light.salon_reading_light"
        output: s2
    switches:
      - name: "Salon Fan"
        output: s3
```

**Key Difference:**
- **v5 dict format**: Output is the dict key (`s1:`, `s2:`) - YAML enforces uniqueness
- **v4 list format**: Output is a property (`output: s1`) - duplicates only caught at runtime

#### Configuration Fields

**bloc9** (required): List of Bloc9 device configurations

Each Bloc9 device has:
- **bus_id** (required): Numeric device ID from CAN bus (typically 2-10)
- **name** (required): Device name shown in Home Assistant device info
- **lights** (optional): Dict (v5) or list (v4) of outputs to expose as dimmable lights
- **switches** (optional): Dict (v5) or list (v4) of outputs to expose as switches

**v5.0.0 Dict Format:** Each entity uses output as key:
- **s1/s2/s3/s4/s5/s6** (key): Bloc9 output identifier
  - **name** (required): Entity display name in Home Assistant
  - **entity_id** (optional): Custom entity ID (e.g., `light.my_custom_name`)

**v4.0.0 List Format:** Each entity is a list item with properties:
- **name** (required): Entity display name in Home Assistant
- **output** (required): Bloc9 output identifier (`s1`, `s2`, `s3`, `s4`, `s5`, or `s6`)
- **entity_id** (optional): Custom entity ID

**Entity ID Generation:**
If entity_id is omitted, it's auto-generated from name by removing special characters, converting to lowercase, and replacing spaces with underscores:
- `"Salon Working Light"` → `light.salon_working_light`
- `"12V Electronics"` → `switch.12v_electronics`
- `"Water Pump #1"` → `switch.water_pump_1`

#### Integrity Checks

The configuration loader performs validation to prevent common errors:
- **Duplicate outputs** (v5): YAML dict keys enforce uniqueness at parse time
- **Duplicate outputs** (v4): Runtime check prevents multiple assignments per device
- **Duplicate entity_ids**: Each entity_id must be unique across all devices
- **Invalid output format**: Output must be s1, s2, s3, s4, s5, or s6
- **Missing required fields**: name is required for all entities (output required in v4 list format)

#### Complete Example

**v5.0.0 Dict Format:**

```yaml
bloc9:
  - bus_id: 1
    name: "Electrical Bloc9"
    switches:
      s1:
        name: "12V Electronics"  # entity_id: switch.12v_electronics
      s2:
        name: "USB Outlets"  # entity_id: switch.usb_outlets

  - bus_id: 7
    name: "Salon Bloc9"
    lights:
      s1:
        name: "Working Light"  # entity_id: light.working_light
      s2:
        name: "Reading Light"
        entity_id: "light.salon_reading"  # Custom entity_id
      s6:
        name: "Ceiling Light"  # entity_id: light.ceiling_light
    switches:
      s3:
        name: "Water Pump"  # entity_id: switch.water_pump

  - bus_id: 10
    name: "Navigation Bloc9"
    lights:
      s4:
        name: "Underwater Light"  # entity_id: light.underwater_light
```

**v4.0.0 List Format (still supported):**

```yaml
bloc9:
  - bus_id: 1
    name: "Electrical Bloc9"
    switches:
      - name: "12V Electronics"
        output: s1
      - name: "USB Outlets"
        output: s2

  - bus_id: 7
    name: "Salon Bloc9"
    lights:
      - name: "Working Light"
        output: s1
      - name: "Reading Light"
        entity_id: "light.salon_reading"
        output: s2
      - name: "Ceiling Light"
        output: s6
    switches:
      - name: "Water Pump"
        output: s3

  - bus_id: 10
    name: "Navigation Bloc9"
    lights:
      - name: "Underwater Light"
        output: s4
```

#### Safety Best Practices

1. **Omit Critical Systems**: Don't expose outputs controlling:
   - Bilge pumps
   - Navigation lights
   - Emergency systems
   - Refrigeration
   
2. **Use Descriptive Names**: Make entity names clear to prevent accidental activation

3. **Choose Appropriate Component**:
   - Use `lights:` for dimmable loads (lighting, fans with dimming)
   - Use `switches:` for binary loads (pumps, outlets, electronics)

4. **Start Small**: Begin with a few non-critical outputs, then expand after testing

#### Migration from Previous Versions

**v4.0.0 - Unified Device Structure (BREAKING CHANGE)**

**What changed**: All entities now belong to a single "Scheiber" device instead of individual devices per output.

**Benefits**:
- Cleaner entity naming: `light.scheiber_<name>` instead of `light.<name>_<name>`
- Simplified device management in Home Assistant
- All Scheiber entities grouped under one device

**Migration steps from v3.x**:
1. **Before upgrading**: Note your current entity IDs and automations
2. **Upgrade** to v4.0.0
3. **In Home Assistant**:
   - Go to Settings → Devices & Services → MQTT
   - Delete old Scheiber device entries (one per Bloc9, one per entity)
4. **Restart the addon** - new unified device will be created
5. **Update automations/scripts** with new entity IDs:
   - Old: `light.main_light_saloon_aft_main_light_saloon_aft`
   - New: `light.scheiber_main_light_saloon_aft`

**Migration from v2.x**

**Old behavior (v2.x)**: All 6 outputs on every detected Bloc9 device were automatically exposed as lights.

**New behavior (v3.0.0+)**: Only outputs explicitly configured in `scheiber.yaml` are exposed.

**Migration steps**:
1. Create `/config/scheiber.yaml` in your Home Assistant configuration directory
2. List all Bloc9 devices you want to integrate (use bus IDs from v2.x discovery)
3. For each device, list only the outputs you want to control
4. Choose `lights:` or `switches:` based on the load type
5. Restart the addon

**Without scheiber.yaml**: The bridge will still monitor CAN traffic and publish to MQTT, but **no entities will appear in Home Assistant** via discovery.

## Troubleshooting MQTT Discovery Updates

### Issue: Home Assistant Not Applying Discovery Config Changes

**Symptom**: After upgrading to a new version with changed MQTT discovery attributes (like v5.0.0's JSON schema), Home Assistant continues controlling devices successfully but doesn't adopt the new discovery configuration.

**Root Cause**: Home Assistant caches MQTT discovery configurations. When an entity already exists with a `unique_id`, Home Assistant will **not update** certain discovery attributes even when new discovery messages are published. This is by design to prevent accidental overwrites of user customizations.

**Attributes that DO update**: 
- `state_topic`, `command_topic`, `availability_topic` (topic references)
- `payload_on`, `payload_off` (payload values)

**Attributes that DO NOT update after initial discovery**:
- `schema` (e.g., changing from default to "json")
- `brightness`, `supported_color_modes` (capability flags)
- `brightness_state_topic`, `brightness_command_topic` (removed in v5.0.0)
- `device` structure changes

### Solution: Clean MQTT Integration Before Upgrading

When upgrading between major versions (especially v3.x → v4.0.0 → v5.0.0), follow these steps:

**Method 1: Delete MQTT Devices (Recommended)**

1. **Before upgrading**:
   - Note your current entity IDs and automations
   - Export/backup any important dashboard configurations
   
2. **In Home Assistant**:
   - Go to **Settings** → **Devices & Services** → **MQTT**
   - Delete all Scheiber-related devices
   - This preserves entity history but allows fresh discovery

3. **Upgrade** the Scheiber addon to new version

4. **Restart** the addon to trigger new discovery messages

5. **Verify** in Home Assistant that entities reappear with new attributes

6. **Update automations/scripts** if entity IDs changed

**Method 2: Deep Clean (If Method 1 Fails)**

If deleting devices through the UI doesn't work:

1. **Stop Home Assistant**

2. **Edit registry files** (⚠️ **Backup first!**):
   - `/homeassistant/.storage/core.entity_registry`
   - `/homeassistant/.storage/core.device_registry`
   
3. **Remove Scheiber entries**:
   - Search for `"platform": "mqtt"` with `"identifiers"` containing `"scheiber"` or `"bloc9"`
   - Delete the entire entity/device JSON objects
   - Ensure JSON remains valid (check commas, brackets)

4. **Clear MQTT retained messages** (optional but recommended):
   ```bash
   # Connect to MQTT broker and clear retained discovery configs
   mosquitto_sub -h <broker> -u <user> -P <pass> -t "homeassistant/#" -v --retained-only | \
     grep "scheiber" | awk '{print $1}' | \
     xargs -I {} mosquitto_pub -h <broker> -u <user> -P <pass> -t {} -r -n
   ```

5. **Start Home Assistant**

6. **Restart Scheiber addon** to publish fresh discovery

**Method 3: Change unique_id (Not Recommended)**

As a last resort, you can modify the addon code to use new `unique_id` values:
- Edit `scheiber/src/devices.py` 
- Change the `unique_id` format in `publish_discovery_config()`
- This creates new entities, leaving old ones orphaned

### Why This Happens

Home Assistant's MQTT Discovery is designed with these principles:

1. **Preserve User Customizations**: Once discovered, entity attributes can be customized in the UI (names, icons, areas). Discovery updates could override these.

2. **Stability Over Freshness**: Frequent re-discovery could cause entities to flicker or lose state during MQTT broker reconnections.

3. **Retained Messages**: MQTT discovery configs are retained at the broker, ensuring devices survive Home Assistant restarts.

This design is generally beneficial but requires manual cleanup during major version upgrades that change entity capabilities.

### References

- [Home Assistant MQTT Discovery Documentation](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)
- [MQTT Discovery Payload Updates](https://www.home-assistant.io/integrations/mqtt/#discovery-payload)
- Home Assistant Community discussions on discovery updates

**Without scheiber.yaml**: The bridge will still monitor CAN traffic and publish to MQTT, but **no entities will appear in Home Assistant** via discovery.

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

### Device Protocol Configuration

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

**Current Version**: 4.0.0

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
- **Solution**: The bridge handles this automatically. Empty payloads are detected early and logged but don't cause errors.
- **Prevention**: Bridge clears retained command messages after execution

**Devices Not Recovering After Timeout**
- **Cause**: Heartbeat updates not triggered on all message types
- **Solution**: Heartbeat updates on ANY matching CAN message (including unchanged status)
- **Check**: Verify CAN bus traffic with `candump can1`

**Brightness Changes Followed by Full Brightness**
- **Cause**: Home Assistant sending ON command after brightness
- **Solution**: Uses `on_command_type: "brightness"` to prevent duplicate commands
- **Verify**: Check discovery config includes correct on_command_type

**Lights Unavailable in Home Assistant UI**
- **Cause**: Old per-property availability system
- **Solution**: Uses heartbeat-based availability (60s timeout)
- **Check**: Look for status messages (0x00000600 prefix) in CAN traffic

**Spinning Loading Indicator After Brightness Change**
- **Cause**: Waiting for state confirmation from bridge
- **Solution**: Implements optimistic state updates for immediate UI feedback
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

## Known Limitations & Warnings

- **Incomplete Protocol**: The Scheiber CAN protocol is reverse-engineered and not fully understood
- **Limited Device Support**: Only Bloc9 switch panels currently implemented
- **No Dimming Protocol**: Brightness control works but underlying protocol not fully decoded
- **Linux Only**: Requires SocketCAN interface (not available on Windows/macOS)

## Version History

### v5.0.0 (December 2025) - BREAKING CHANGE
**JSON Schema + Dict-Based Configuration**
- Lights now use JSON schema for state/command topics: `{"state": "ON", "brightness": 255}`
- New dict-based config format: `lights: s1: name: "Light"` (recommended, prevents duplicates)
- v4 list format still supported: `lights: - name: "Light" output: s1`
- Transition support logged but not yet implemented in CAN protocol
- Removed separate brightness topics (brightness_state_topic, brightness_command_topic)
- Breaking: MQTT topic structure changed - requires Home Assistant entity reconfiguration

**Migration from v4.0.0 to v5.0.0:**
1. **Optional**: Update `scheiber.yaml` to dict format for better duplicate prevention
2. **Required**: Restart addon to publish new JSON schema discovery configs
3. Home Assistant will auto-discover updated entities (may require clearing old configs)

### v4.0.0 (December 2025) - BREAKING CHANGE
**Unified Device Structure**
- All entities now belong to single "Scheiber" device in Home Assistant
- Simplified entity naming: `light.scheiber_<name>` instead of repetitive names
- Removed individual device entries per output
- Removed Bloc9 sensor devices
- Device identifier: `scheiber_system`
- Breaking: Requires manual cleanup of old devices and automation updates

### v3.1.6 (December 2025)
- Fixed: Devices going offline when state unchanged for >60s
- Heartbeat now updates on ANY CAN message, even if data unchanged

### v3.x Series (December 2025)
- Explicit entity configuration via `scheiber.yaml`
- Safety controls: only expose configured outputs
- Config integrity checks (duplicate detection)
- Choice of lights vs switches per output
- Hierarchical device structure (removed in v4.0.0)

### v2.x Series (December 2025)
- Heartbeat-based availability tracking
- Optimistic state updates
- Retained message handling
- State persistence between restarts

### v1.x Series (December 2025)
- Initial MQTT Discovery implementation
- Basic Bloc9 ON/OFF control
- Brightness control (partially working)

### v0.x Series (November-December 2025)
- Reverse engineering phase
- Protocol discovery
- CAN message analysis tools
- Initial bridge architecture
- **No Automated Tests**: Testing requires physical hardware
- **Breaking Changes Expected**: Protocol understanding may change, requiring config updates
- **Experimental Status**: Use at your own risk, functionality may be incomplete or incorrect

## References

- [python-can documentation](https://python-can.readthedocs.io/)
- [Paho MQTT Python](https://eclipse.dev/paho/index.php?page=clients/python/index.php)
- [Home Assistant MQTT Integration](https://www.home-assistant.io/integrations/mqtt/)
- Sample CAN dumps in `scheiber/tools/data/`
- Device mapping in `scheiber/tools/can_names.csv`

## License

See repository license file.

## Contributing

This is an **active reverse-engineering project**. The CAN protocol is not officially documented, and much of the functionality is based on observation and experimentation. Contributions are welcome, especially:

- CAN message captures from different Scheiber devices
- Protocol analysis and documentation
- Bug reports with detailed logs and CAN dumps
- Testing on different hardware configurations

**Expect significant changes** as our understanding of the protocol evolves. This project may have bugs, incomplete features, or incorrect protocol interpretations.