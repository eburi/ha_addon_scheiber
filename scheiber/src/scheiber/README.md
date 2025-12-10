# Scheiber Python Module

Python library for controlling Scheiber marine lighting devices over CAN bus.

## Features

- **Factory-based initialization** - Simple setup with YAML configuration
- **Device abstraction** - High-level API for Bloc9 and other devices
- **Smooth transitions** - Fade lights with configurable duration and easing
- **Flash effects** - Attention-grabbing flash patterns
- **State persistence** - Automatic save/restore of device state
- **Observer pattern** - Subscribe to device and CAN bus events
- **Read-only mode** - Monitor CAN bus without sending commands

## Quick Start

```python
from scheiber import create_scheiber_system

# Create system from config file
system = create_scheiber_system(
    can_interface='can0',
    config_path='scheiber.yaml',
    state_file='scheiber_state.json'
)

# Get a device
device = system.get_device('bloc9', bus_id=3)

# Get a light
light = device.get_light('s1')

# Control the light
light.set_brightness(200)
light.fade_to(255, duration_ms=2000)
light.flash(count=3)

# Subscribe to changes
def on_change(prop, value):
    print(f"Light {prop} changed to {value}")

light.subscribe(on_change)

# Start listening
system.start()

# Stop when done
system.stop()
```

## CLI Tool

The `scheiber-cli` command-line tool provides easy access to Scheiber devices:

```bash
# Listen to CAN bus with auto-discovery
./scheiber-cli listen can0

# Use a specific config file
./scheiber-cli listen can0 --config /path/to/scheiber.yaml

# Save/restore state
./scheiber-cli listen can0 --state scheiber_state.json

# Read-only mode (no commands sent)
./scheiber-cli listen can0 --read-only

# Enable debug logging
./scheiber-cli listen can0 --log-level debug
```

## Configuration

Create a `scheiber.yaml` file to define your devices:

```yaml
devices:
  - type: bloc9
    bus_id: 3
    name: "Saloon Lights"
    lights:
      S1:
        name: "Overhead Light"
        initial_brightness: 128
      S2:
        name: "Reading Light"
        initial_brightness: 0
```

See `scheiber.example.yaml` in the repository root for a complete example.

## Architecture

The module follows a layered architecture:

- **ScheiberCanBus** - Low-level CAN I/O wrapper
- **ScheiberSystem** - Device manager and message router
- **ScheiberCanDevice** - Abstract base class for devices
- **Bloc9Device** - Implementation for Bloc9 controllers
- **DimmableLight** - Light component with transitions and effects
- **Switch** - Basic ON/OFF control component

See `IMPLEMENTATION.md` for detailed architecture documentation.

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Format code
black scheiber/
```

## License

See LICENSE file in repository root.
