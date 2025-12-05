# Device Class Refactoring (v1.1.0)

## Overview

The MQTT bridge has been refactored to use an object-oriented device class hierarchy, making it easy to add support for new device types.

## Architecture

### Class Hierarchy

```
ScheiberCanDevice (Abstract Base Class)
    ├── Light (Bloc9 switches with brightness)
    ├── TankSensor (future)
    ├── BatteryMonitor (future)
    └── ... (extensible)
```

### Files

- **`devices.py`**: Device class definitions
  - `ScheiberCanDevice`: Abstract base class with common functionality
  - `Light`: Concrete class for lights with brightness support
  - `DEVICE_TYPE_CLASSES`: Registry mapping device types to classes
  - `create_device()`: Factory function

- **`mqtt_bridge.py`**: Main bridge application (simplified)
  - Creates device instances using `create_device()`
  - Delegates discovery and publishing to device instances
  - Removed hardcoded light-specific logic

## Device Class API

### ScheiberCanDevice (Base Class)

**Abstract Methods** (must be implemented by subclasses):
- `publish_discovery_config()`: Publish Home Assistant MQTT Discovery config
- `publish_state(property_name, value)`: Publish property state to MQTT

**Common Methods** (inherited by all devices):
- `__init__(device_type, device_id, device_config, mqtt_client, mqtt_topic_prefix)`
- `get_all_properties()`: Get all properties from device_types.yaml
- `update_state(decoded_properties)`: Update internal state
- `publish_device_info()`: Publish device metadata

**Attributes**:
- `device_type`: Device type string (e.g., "bloc9")
- `device_id`: Device bus ID
- `device_config`: Configuration from device_types.yaml
- `mqtt_client`: MQTT client instance
- `mqtt_topic_prefix`: MQTT topic prefix
- `state`: Current device state dict
- `logger`: Per-device logger

### Light Class

**Features**:
- Publishes Home Assistant light entity discovery configs
- Supports brightness with 0-100 scale
- Filters out internal properties (stat*, _brightness)
- Publishes brightness to `/brightness` sub-topic

**Implementation**:
- Overrides `publish_discovery_config()` to add brightness support
- Overrides `publish_state()` to handle brightness properties separately

## Adding New Device Types

### Step 1: Create Device Class

```python
# In devices.py

class TankSensor(ScheiberCanDevice):
    """Tank level sensor device."""
    
    def publish_discovery_config(self):
        """Publish HA sensor discovery config."""
        # Implement sensor-specific discovery
        all_properties = self.get_all_properties()
        
        for prop_name in all_properties:
            # Create sensor entity config
            config_payload = {
                "name": f"Tank {self.device_id} {prop_name}",
                "state_topic": f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{prop_name}/state",
                "unit_of_measurement": "%",
                "device_class": "volume",
                # ... etc
            }
            # Publish config...
    
    def publish_state(self, property_name: str, value: Any):
        """Publish tank sensor state."""
        # Implement sensor-specific state publishing
        topic = f"{self.mqtt_topic_prefix}/scheiber/{self.device_type}/{self.device_id}/{property_name}/state"
        self.mqtt_client.publish(topic, str(value), qos=1, retain=True)
```

### Step 2: Register Device Class

```python
# In devices.py

DEVICE_TYPE_CLASSES = {
    "bloc9": Light,
    "tank_sensor": TankSensor,  # Add new mapping
    # ...
}
```

### Step 3: Add Device Type to device_types.yaml

```yaml
tank_sensor:
  name: "Tank Sensor"
  bus_id_extractor:
    type: "formula"
    formula: "((arb_id & 0xFF) >> 4)"
  matchers:
    - address: 0x00FF0000
      mask: 0xFFFF0000
      name: "Tank level"
      properties:
        level:
          template: "[0]"
          formatter: "{}"
```

### Step 4: Test

That's it! The bridge will automatically:
1. Detect devices of the new type
2. Create instances using `create_device()`
3. Call device-specific methods for discovery and state publishing

## Migration Notes

### What Changed

**Before (v1.0.x)**:
- `mqtt_bridge.py` contained all device-specific logic
- Hardcoded light/brightness handling
- Adding new device types required modifying main bridge code

**After (v1.1.0)**:
- Device-specific logic moved to device classes
- Bridge delegates to device instances
- New device types only require new class + YAML config

### Backward Compatibility

- MQTT topics unchanged
- Discovery config format unchanged
- Command handling unchanged
- No breaking changes for existing integrations

## Benefits

1. **Separation of Concerns**: Device logic separated from bridge logic
2. **Extensibility**: Easy to add new device types
3. **Maintainability**: Changes to one device type don't affect others
4. **Testability**: Device classes can be tested independently
5. **Code Reuse**: Common functionality in base class

## Future Enhancements

- Add command handling to device classes (not just publishing)
- Support for device-specific command processors
- Dynamic device discovery without YAML
- Device class plugins/extensions
