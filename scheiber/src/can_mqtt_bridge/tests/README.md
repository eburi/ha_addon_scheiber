# can_mqtt_bridge Tests

Test suite for the CAN MQTT Bridge module.

## Running Tests

From the `scheiber/src/can_mqtt_bridge` directory:

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest -v tests/

# Run specific test file
pytest tests/test_bridge.py

# Run specific test class
pytest tests/test_bridge.py::TestMQTTBridgeInit

# Run specific test
pytest tests/test_bridge.py::TestMQTTBridgeInit::test_initialization_minimal

# Run with coverage
pytest --cov=can_mqtt_bridge --cov-report=html tests/
```

## Test Structure

```
tests/
├── __init__.py          # Package marker
├── conftest.py          # Shared fixtures
└── test_bridge.py       # MQTTBridge tests
```

## Test Coverage

### Test Classes

1. **TestMQTTBridgeInit** - Initialization tests
   - Minimal parameters
   - Full parameters
   - MQTT connection failure

2. **TestMQTTBridgeStartStop** - Lifecycle tests
   - Start bridge
   - Stop bridge
   - Idempotent start/stop

3. **TestMQTTDiscoveryLights** - Light discovery tests
   - Discovery config structure
   - Availability publishing
   - Command subscription
   - JSON schema compliance

4. **TestMQTTDiscoverySwitches** - Switch discovery tests
   - Discovery config structure
   - Switch-specific payloads

5. **TestStatePublishing** - State change tests
   - Light state changes
   - Switch state changes
   - JSON state format

6. **TestCommandHandling** - MQTT command tests
   - Brightness commands
   - ON/OFF commands
   - Fade transitions
   - Flash effects
   - Read-only mode

7. **TestTopicPrefix** - Custom prefix tests
   - Custom topic prefix usage

## Key Test Features

- **Mocking**: All CAN and MQTT operations are mocked
- **Observer pattern**: Tests verify callbacks are registered
- **MQTT Discovery**: Validates Home Assistant compatibility
- **JSON schema**: Ensures v5.0.0+ compliance
- **Unified device**: Verifies scheiber_system device structure
- **Availability**: Checks online status publishing

## Fixtures (conftest.py)

- `mock_mqtt_client` - Mock MQTT client
- `mock_scheiber_system` - Mock Scheiber system
- `mock_light` - Mock DimmableLight
- `mock_switch` - Mock Switch
- `mock_bloc9_device` - Mock Bloc9Device
- `temp_config_file` - Temporary config file

## Running in CI/CD

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-mock

# Run tests with coverage
pytest --cov=can_mqtt_bridge --cov-report=term-missing tests/

# Generate HTML coverage report
pytest --cov=can_mqtt_bridge --cov-report=html tests/
```

## Test Philosophy

1. **Unit tests** - Test individual components in isolation
2. **Mock external dependencies** - No real CAN bus or MQTT broker needed
3. **Verify contracts** - Ensure proper API usage
4. **Check integration points** - Validate observer patterns and callbacks
5. **Validate MQTT compliance** - Ensure Home Assistant compatibility

## Adding New Tests

When adding new features to MQTTBridge:

1. Add test class in `test_bridge.py`
2. Use appropriate fixtures from `conftest.py`
3. Mock external dependencies (MQTT, CAN, system)
4. Verify both success and failure cases
5. Check MQTT topic structure and payloads
6. Ensure read-only mode is respected

## Common Test Patterns

### Testing MQTT Discovery

```python
@patch("can_mqtt_bridge.bridge.mqtt.Client")
@patch("can_mqtt_bridge.bridge.create_scheiber_system")
def test_discovery(mock_create_system, mock_mqtt_client):
    # Setup mocks
    mock_system = MagicMock()
    mock_create_system.return_value = mock_system
    
    # Start bridge
    bridge = MQTTBridge(...)
    bridge.start()
    
    # Verify MQTT publishes
    calls = mock_client.publish.call_args_list
    # ... assertions
```

### Testing State Changes

```python
# Capture observer callback
callback_holder = []
mock_light.subscribe = lambda cb: callback_holder.append(cb)

# Start bridge (registers callback)
bridge.start()

# Trigger state change
callback_holder[0]({"state": True, "brightness": 200})

# Verify MQTT publish
# ... assertions
```

### Testing Commands

```python
# Setup bridge
bridge.start()

# Simulate MQTT message
msg = MagicMock()
msg.topic = "homeassistant/scheiber/bloc9/7/s1/set"
msg.payload = b'{"brightness": 150}'

bridge._on_mqtt_message(None, None, msg)

# Verify device method called
mock_light.set_brightness.assert_called_once_with(150)
```
