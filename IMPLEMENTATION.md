
# Scheiber Module Architecture

## Overview

Refactor `scheiber_device.py` into a proper `scheiber/` module with clear separation of concerns between CAN bus management, device abstraction, and client integrations (MQTT, CLI).

## Goals

1. **Client-agnostic CAN bus layer**: Separate CAN bus logic from MQTT bridge
2. **Clean API**: Factory pattern for initialization, simple device access
3. **Maintainable code**: One file per class, clear architecture boundaries
4. **State persistence**: Robust state saving and restoration
5. **Future-proof**: Easy to add new device types (Bloc7, etc.)

---

## Module Structure

```
scheiber/
├── __init__.py              # Public API: factory method
├── can_bus.py               # ScheiberCanBus: Low-level CAN bus I/O
├── system.py                # ScheiberSystem: Device manager, state persistence
├── base_device.py           # ScheiberCanDevice: Abstract base class
├── bloc9.py                 # Bloc9Device implementation
├── switch.py                # Switch class (basic on/off)
├── light.py                 # DimmableLight class (composition over Switch)
├── transitions.py           # TransitionController, FlashController (existing)
└── matchers.py              # Message matching utilities
```

---

## Architecture Components

### 1. Factory Method (scheiber/__init__.py)

**Public API:**
```python
def create_scheiber_system(
    can_interface: str,
    config_path: str,           # Path to scheiber.yaml
    state_file: Optional[str],  # Path to scheiber.state.yaml
    log_level: str = "info"
) -> ScheiberSystem
```

**Returns:** `ScheiberSystem` instance ready to use

**Responsibilities:**
- Parse configuration file
- Validate device configurations (unique bus_id per device_type)
- Create device instances
- Initialize ScheiberCanBus and ScheiberSystem
- Load and restore state

---

### 2. ScheiberCanBus (scheiber/can_bus.py)

**Low-level CAN bus wrapper**

**Responsibilities:**
- Open/close CAN socket (python-can)
- Send CAN messages (with optional read-only mode)
- Provide raw message sending interface to devices
- Track basic I/O statistics

**API:**
```python
class ScheiberCanBus:
    def __init__(self, interface: str, read_only: bool = False):
        pass
    
    def send_message(self, arbitration_id: int, data: bytes) -> None:
        """Send CAN message if not in read-only mode."""
        pass
    
    def start_listening(self, on_message_callback: Callable) -> None:
        """Start listening for CAN messages, call callback for each."""
        pass
    
    def stop(self) -> None:
        """Stop listening and close CAN bus."""
        pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Return CAN bus I/O statistics."""
        pass
```

**Observer Pattern:**
- Implements observer pattern for bus statistics updates
- Notifies subscribers periodically (e.g., every 10 seconds)

---

### 3. ScheiberSystem (scheiber/system.py)

**High-level device manager**

**Responsibilities:**
- Manage device instances
- Route incoming CAN messages to appropriate devices via matchers
- Coordinate state persistence (periodically, not on every message)
- Provide device access API for clients
- Track bus statistics and unknown messages

**API:**
```python
class ScheiberSystem:
    def __init__(self, can_bus: ScheiberCanBus, devices: List[ScheiberCanDevice]):
        pass
    
    def get_device(self, device_type: str, bus_id: int) -> Optional[ScheiberCanDevice]:
        """Get device by type and bus ID."""
        pass
    
    def get_all_devices(self) -> List[ScheiberCanDevice]:
        """Get all registered devices."""
        pass
    
    def restore_state(self, state_data: Dict[str, Any]) -> None:
        """Restore state for all devices."""
        pass
    
    def save_state(self) -> Dict[str, Any]:
        """Collect state from all devices for persistence."""
        pass
    
    def start(self) -> None:
        """Start CAN message processing."""
        pass
    
    def stop(self) -> None:
        """Stop CAN message processing."""
        pass
    
    def subscribe_to_stats(self, callback: Callable) -> None:
        """Subscribe to bus statistics updates."""
        pass
```

**Message Routing:**
- Each device provides matchers (pattern/mask for arbitration IDs)
- On incoming message, check all matchers, route to matching device
- Track unknown arbitration IDs, log once per ID

**State Persistence:**
- Save state periodically (e.g., every 30 seconds) if changes detected
- Save on shutdown
- **Not** after every CAN message (excessive I/O)

---

### 4. ScheiberCanDevice (scheiber/base_device.py)

**Abstract base class for all device types**

**Responsibilities:**
- Define device interface
- Provide matchers for message routing
- Handle state serialization/deserialization
- Manage child components (switches, lights)

**API:**
```python
class ScheiberCanDevice(ABC):
    def __init__(self, device_id: int, can_bus: ScheiberCanBus):
        pass
    
    @abstractmethod
    def get_matchers(self) -> List[Matcher]:
        """Return list of matchers for this device's CAN messages."""
        pass
    
    @abstractmethod
    def process_message(self, msg: can.Message) -> None:
        """Process incoming CAN message that matched this device."""
        pass
    
    @abstractmethod
    def restore_from_state(self, state: Dict[str, Any]) -> None:
        """Restore device state from persisted data."""
        pass
    
    @abstractmethod
    def store_to_state(self) -> Dict[str, Any]:
        """Return current state for persistence."""
        pass
    
    def get_switches(self) -> List[Switch]:
        """Return list of switches (if any)."""
        return []
    
    def get_lights(self) -> List[DimmableLight]:
        """Return list of dimmable lights (if any)."""
        return []
```

---

### 5. Bloc9Device (scheiber/bloc9.py)

**Bloc9-specific implementation**

**Responsibilities:**
- Implement Bloc9 CAN protocol
- Manage 6 dimmable lights (S1-S6)
- Provide matchers for Bloc9 messages (status, commands)
- Handle state persistence

**Matchers (v6.1.0+ Architecture):**
- **Outputs define their own matchers** via `get_matchers()` method
- **No property field**: Matchers use only pattern/mask (property was removed as unnecessary)
- **Full 32-bit matching**: Mask is 0xFFFFFFFF to include device ID byte (prevents cross-device pollution)
- **Direct dispatch**: `_matcher_to_outputs` maps arbitration_id → List[Output]
- Device ID encoding: `(device_id << 3) | 0x80` for all message types

**Critical Fix (v6.1.0):**
Previous implementation used 0xFFFFFF00 mask, causing cross-device side effects.
Message 0x021806D0 (device 10, S3/S4) matched ALL devices because mask ignored low byte.
Solution: Use 0xFFFFFFFF mask to include full arbitration ID.

**Example:**
```python
class Bloc9Device(ScheiberCanDevice):
    def __init__(self, ...):
        # ... create lights and switches ...
        
        # Build matcher mapping (called automatically at end of __init__)
        self.get_matchers()
    
    def get_matchers(self) -> List[Matcher]:
        """Delegate to outputs and build dispatch mapping."""
        matchers = []
        self._matcher_to_outputs = {}  # Clear and rebuild
        
        # Collect matchers from all lights
        for light in self.lights:
            for matcher in light.get_matchers():
                pattern = matcher.pattern
                if pattern not in self._matcher_to_outputs:
                    self._matcher_to_outputs[pattern] = []
                    matchers.append(matcher)
                self._matcher_to_outputs[pattern].append(light)
        
        # Collect matchers from all switches (same pattern)
        for switch in self.switches:
            for matcher in switch.get_matchers():
                pattern = matcher.pattern
                if pattern not in self._matcher_to_outputs:
                    self._matcher_to_outputs[pattern] = []
                    matchers.append(matcher)
                self._matcher_to_outputs[pattern].append(switch)
        
        # Add heartbeat and command echo matchers
        heartbeat_pattern = 0x00000600 | ((self.device_id << 3) | 0x80)
        matchers.append(Matcher(pattern=heartbeat_pattern, mask=0xFFFFFFFF))
        
        command_id = 0x02360600 | ((self.device_id << 3) | 0x80)
        matchers.append(Matcher(pattern=command_id, mask=0xFFFFFFFF))
        
        return matchers
    
    def process_message(self, msg: can.Message) -> None:
        """Process incoming CAN message using direct dispatch."""
        # Check heartbeat (device-level)
        heartbeat_pattern = 0x00000600 | ((self.device_id << 3) | 0x80)
        if msg.arbitration_id == heartbeat_pattern:
            self._process_status(msg)
            return
        
        # Ignore command echo
        command_id = 0x02360600 | ((self.device_id << 3) | 0x80)
        if msg.arbitration_id == command_id:
            return
        
        # Direct dispatch to outputs
        outputs = self._matcher_to_outputs.get(msg.arbitration_id, [])
        if outputs:
            for output in outputs:
                output.process_matching_message(msg)
```

**Output Base Class:**
```python
class Output:
    def get_matchers(self) -> List[Matcher]:
        """Return matchers for this output's CAN messages."""
        # Determine message type based on switch_nr
        if self.switch_nr in (0, 1):  # S1, S2
            base_pattern = 0x02160600
        elif self.switch_nr in (2, 3):  # S3, S4
            base_pattern = 0x02180600
        elif self.switch_nr in (4, 5):  # S5, S6
            base_pattern = 0x021A0600
        
        # Add device ID (with 0x80 bit)
        pattern = base_pattern | ((self.device_id << 3) | 0x80)
        
        # Use full 32-bit mask to prevent cross-device pollution
        return [Matcher(pattern=pattern, mask=0xFFFFFFFF)]
    
    def process_matching_message(self, msg: can.Message) -> None:
        """Process a CAN message that matched this output."""
        state, brightness = self.get_state_from_can_message(msg, self.switch_nr)
        # Update state and notify observers...
```

---

### 6. Switch and DimmableLight (scheiber/switch.py, scheiber/light.py)

**Component classes for device outputs**

**Design Decision:** Use **composition** instead of inheritance
- Switch: Basic ON/OFF control
- DimmableLight: Contains a Switch, adds brightness/fade/flash

**Switch API:**
```python
class Switch:
    def __init__(self, device_id: int, switch_nr: int, can_bus: ScheiberCanBus):
        pass
    
    def set(self, state: bool) -> None:
        """Turn switch ON or OFF."""
        pass
    
    def subscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Subscribe to state changes (observer pattern)."""
        pass
    
    def get_state(self) -> bool:
        """Get current state."""
        pass
```

**DimmableLight API:**
```python
class DimmableLight:
    def __init__(self, device_id: int, switch_nr: int, can_bus: ScheiberCanBus):
        self.switch = Switch(device_id, switch_nr, can_bus)
        self.transition_controller = TransitionController(...)
        self.flash_controller = FlashController(...)
    
    def set(
        self, 
        state: bool, 
        brightness: Optional[int] = None,
        flash: float = 0.0,
        fade_to: Optional[int] = None,
        fade_duration: float = 1.0,
        fade_easing: str = "ease_in_out_sine"
    ) -> None:
        """
        Control light with multiple options.
        
        Args:
            state: True=ON, False=OFF
            brightness: 0-255 (None=use previous, 0=OFF)
            flash: Flash duration in seconds (overrides other params)
            fade_to: Target brightness for fade (None=no fade)
            fade_duration: Fade duration in seconds
            fade_easing: Easing function name
        """
        pass
    
    def subscribe(self, callback: Callable[[str, Any], None]) -> None:
        """Subscribe to state/brightness changes."""
        pass
    
    def get_state(self) -> Dict[str, Any]:
        """Return {"state": bool, "brightness": int}."""
        pass
```

**Flash Behavior (Future Enhancement):**
> **Current implementation:** Simple flash - turn ON at full brightness, then restore previous state.
>
> **Future complex logic:** Flash effect adapts to current brightness:
> - If brightness > 170 (2/3 of 255): Flash OFF (turn off for flash duration)
> - If brightness ≤ 170 or OFF: Flash ON (turn on for flash duration)
> - Always restore to previous state after flash
> - If transition is running: Use fade_to target as restore state instead of current
>
> This provides visual feedback regardless of current light state, but is **deferred** for later implementation.

**Observer Pattern:**
- Switches and lights notify subscribers of state changes
- Clients (MQTT bridge) subscribe to individual lights/switches
- No polling required

---

## Client Integration

### MQTT Bridge Usage

```python
from scheiber import create_scheiber_system

# Initialize scheiber system
scheiber_system = create_scheiber_system(
    can_interface="can0",
    config_path="/data/scheiber.yaml",
    state_file="/data/scheiber.state.yaml",
    log_level="info"
)

# Create MQTT bridge with scheiber system
bridge = MQTTBridge(
    mqtt_host="localhost",
    mqtt_port=1883,
    mqtt_user="mqtt_user",
    mqtt_password="mqtt",
    mqtt_topic_prefix="homeassistant",
    scheiber_system=scheiber_system,
    log_level="info"
)

# Start both
scheiber_system.start()
bridge.run()
```

**MQTTBridge responsibilities (simplified):**
1. Get devices from scheiber_system
2. Subscribe to each light/switch for state changes
3. Publish Home Assistant discovery configs
4. Handle MQTT command messages → call light/switch methods
5. Publish state updates when notified by observers

**What MQTTBridge does NOT do:**
- CAN bus management (handled by scheiber module)
- Message decoding (handled by devices)
- Transition management (handled by lights)
- State persistence (handled by scheiber system)

---

## Implementation Strategy

### Phase 1: Module Structure
1. Create `scheiber/` directory with `__init__.py`
2. Move and refactor classes into separate files
3. Implement factory method

### Phase 2: Core Components
1. Implement ScheiberCanBus (CAN I/O wrapper)
2. Implement ScheiberSystem (device manager, message router)
3. Update base device class

### Phase 3: Device Implementation
1. Refactor Bloc9Device with hardcoded matchers
2. Split Switch and DimmableLight (composition)
3. Keep TransitionController and FlashController as-is

### Phase 4: Client Integration
1. Refactor MQTTBridge to use scheiber module
2. Update CLI tools to use scheiber module
3. Update tests

### Phase 5: State Persistence
1. Implement periodic state saving in ScheiberSystem
2. Implement state restoration on startup
3. Handle migration for old state formats

---

## Design Decisions Summary

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| **Event notification** | Observer pattern | Real-time updates, no polling overhead |
| **Flash behavior** | Keep simple (defer complex logic) | Current implementation works, complex logic is future enhancement |
| **Matcher storage** | Hardcoded in device classes | Efficient once protocol known, still human-readable |
| **Architecture** | ScheiberCanBus + ScheiberSystem | Clear separation: I/O vs device management |
| **Switch vs Light** | Composition | Avoids inheritance issues, more flexible |
| **State persistence** | Periodic (not per-message) | Avoid excessive disk I/O |
| **File organization** | One file per class | Clear changesets, better maintainability |

---

## Migration Notes

- Existing tests continue to work with minimal changes
- MQTT bridge API changes, but functionality preserved
- CLI tools need updates to use factory method
- State file format can remain backward-compatible 

---

## Version 5.4.0: CAN MQTT Bridge v6 Preview

### Overview

Version 6.0.0 introduces `can_mqtt_bridge` - a complete rewrite of the MQTT bridge using the new scheiber module architecture. This provides cleaner code, better separation of concerns, and improved maintainability.

### Architecture

```
can_mqtt_bridge/
├── __init__.py          # Module exports
├── __main__.py          # CLI entry point with argparse
└── bridge.py            # MQTTBridge class
```

**Entry Point:** `scheiber/src/can-mqtt-bridge` (executable script)

### MQTTBridge Class (bridge.py)

**Responsibilities:**
1. Initialize scheiber system via factory method
2. Connect to MQTT broker with paho-mqtt
3. Setup Home Assistant MQTT Discovery for all devices
4. Subscribe to device state changes via observer pattern
5. Publish state updates to MQTT
6. Handle MQTT command messages from Home Assistant
7. Provide clean shutdown

**Key Features:**
- **Observer Pattern**: Subscribe to light/switch changes, publish to MQTT automatically
- **Home Assistant Discovery**: Auto-configure entities in Home Assistant
- **Unified Device**: All entities belong to single "Scheiber" device
- **JSON Command Schema**: Full support for brightness, transitions, and flash
- **Read-Only Mode**: Monitor CAN bus without sending commands
- **Automatic Reconnection**: MQTT client handles reconnection automatically

### Home Assistant Discovery

**Discovery Config:**
```python
{
    "name": "Scheiber S1",
    "unique_id": "scheiber_bloc9_3_s1",
    "device": {
        "identifiers": ["scheiber_system"],
        "name": "Scheiber",
        "manufacturer": "Scheiber",
        "model": "Marine Lighting Control System"
    },
    "state_topic": "homeassistant/scheiber/bloc9/3/s1/state",
    "command_topic": "homeassistant/scheiber/bloc9/3/s1/set",
    "brightness_state_topic": "homeassistant/scheiber/bloc9/3/s1/brightness",
    "brightness_command_topic": "homeassistant/scheiber/bloc9/3/s1/set_brightness",
    "brightness_scale": 255,
    "schema": "json"
}
```

**Entity Naming:**
- Entity ID: `light.scheiber_s1` (cleaner than `light.s1_s1`)
- Friendly Name: "Scheiber S1"
- Device: "Scheiber - Marine Lighting Control System"

### MQTT Topics

**Pattern:** `{prefix}/scheiber/{device_type}/{bus_id}/{light_name}/{suffix}`

**State Topics:**
- State: `{prefix}/scheiber/bloc9/3/s1/state` → "ON" or "OFF"
- Brightness: `{prefix}/scheiber/bloc9/3/s1/brightness` → 0-255

**Command Topics:**
- State/JSON: `{prefix}/scheiber/bloc9/3/s1/set` → JSON or "ON"/"OFF"
- Brightness: `{prefix}/scheiber/bloc9/3/s1/set_brightness` → 0-255

**Discovery:**
- Config: `{prefix}/light/{unique_id}/config` → JSON discovery payload

### Command Handling

**Simple Commands:**
```json
"ON"              → Set brightness to 255
"OFF"             → Set brightness to 0
```

**JSON Commands:**
```json
{
  "state": "ON",           // ON/OFF
  "brightness": 200        // 0-255
}

{
  "state": "ON",
  "brightness": 255,
  "transition": 2.0        // Fade over 2 seconds
}

{
  "state": "ON",
  "flash": "short"         // Flash 3 times (short) or 5 times (long)
}
```

**Command Processing:**
1. Parse JSON or simple ON/OFF string
2. Check for flash effect → call `light.flash(count)`
3. Check for transition → call `light.fade_to(target, duration_ms)`
4. Otherwise → call `light.set_brightness(value)`

### Usage

**Command Line:**
```bash
can-mqtt-bridge \
    --can-interface can0 \
    --mqtt-host localhost \
    --mqtt-port 1883 \
    --mqtt-user mqtt_user \
    --mqtt-password mqtt \
    --mqtt-topic-prefix homeassistant \
    --config /config/scheiber.yaml \
    --data-dir /data \
    --log-level info
```

**Home Assistant Addon:**
- Config option: `run_dev_version: true` enables new bridge
- Config option: `run_dev_version: false` uses old mqtt_bridge.py (v5.3.6)
- Seamless transition - no breaking changes for users

**run.sh Logic:**
```bash
if [ "${RUN_DEV_VERSION}" = "true" ]; then
    exec python3 can-mqtt-bridge ...  # Version 6.0.0
else
    exec python3 mqtt_bridge.py ...   # Version 5.3.6
fi
```

### State Flow

**CAN → MQTT (Incoming):**
1. CAN message arrives at ScheiberCanBus
2. ScheiberSystem routes to Bloc9Device via matchers
3. Bloc9Device updates DimmableLight state
4. DimmableLight notifies observers (MQTTBridge callback)
5. MQTTBridge publishes state/brightness to MQTT

**MQTT → CAN (Commands):**
1. MQTT command arrives (e.g., `{"state": "ON", "brightness": 200}`)
2. MQTTBridge parses command, finds light by topic
3. Calls `light.set_brightness(200)` or `light.fade_to(255, duration_ms=2000)`
4. Light cancels any active transitions
5. Light updates internal state and sends CAN command via ScheiberCanBus
6. State change triggers observer notification → MQTT publish (echo)

### Benefits Over Old Bridge

1. **Cleaner Architecture**: Scheiber module handles all CAN/device logic
2. **No Dual Tracking**: Single source of truth (scheiber module), MQTT just subscribes
3. **Simpler Code**: MQTTBridge is ~280 lines vs old bridge ~500+ lines
4. **Better Testing**: Can test scheiber module independently of MQTT
5. **Future-Proof**: Easy to add new device types (Bloc7, etc.)
6. **State Persistence**: Handled by scheiber system, not MQTT bridge
7. **Unified Device**: All entities in Home Assistant belong to single device

### Migration Path

**Phase 1 (Current):**
- Both bridges coexist in codebase
- Users opt-in via `run_dev_version` flag
- Default remains old bridge (v5.3.6)

**Phase 2 (Future):**
- After testing, flip default to new bridge
- Old bridge remains available with `run_dev_version: false`

**Phase 3 (Long-term):**
- Remove old bridge code after stable period
- New bridge becomes only option

### Configuration

**Old Bridge (mqtt_bridge.py):**
- Uses environment variables or command-line args
- No scheiber.yaml config file
- Device IDs hardcoded or discovered

**New Bridge (can-mqtt-bridge):**
- Requires `scheiber.yaml` config file (optional for auto-discovery)
- Clean YAML-based device configuration
- Example: `scheiber.example.yaml` in repo root

---

