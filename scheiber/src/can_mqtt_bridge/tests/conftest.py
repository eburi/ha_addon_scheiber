"""
Shared fixtures for can_mqtt_bridge tests.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def mock_mqtt_client():
    """Mock MQTT client."""
    client = MagicMock()
    client.connect.return_value = 0
    client.subscribe.return_value = (0, 1)
    client.publish.return_value = MagicMock(rc=0)
    return client


@pytest.fixture
def mock_scheiber_system():
    """Mock Scheiber system."""
    system = MagicMock()
    system.get_all_devices.return_value = []
    return system


@pytest.fixture
def mock_light():
    """Mock DimmableLight."""
    light = MagicMock()
    light.name = "s1"
    light.get_state.return_value = {"state": False, "brightness": 0}
    light.subscribe = Mock()
    light.get_lights.return_value = []
    light.get_switches.return_value = []
    return light


@pytest.fixture
def mock_switch():
    """Mock Switch."""
    switch = MagicMock()
    switch.name = "Switch 1"
    switch.entity_id = "switch_1"
    switch.get_state.return_value = False
    switch.subscribe = Mock()
    return switch


@pytest.fixture
def mock_bloc9_device(mock_light, mock_switch):
    """Mock Bloc9Device."""
    device = MagicMock()
    device.__class__.__name__ = "Bloc9Device"
    device.device_id = 7
    device.get_lights.return_value = [mock_light]
    device.get_switches.return_value = [mock_switch]
    return device


@pytest.fixture
def temp_config_file(tmp_path):
    """Create temporary config file."""
    config = tmp_path / "test_config.yaml"
    config.write_text(
        """
bloc9_devices:
  7:
    name: "Test Panel"
    lights:
      s1:
        name: "S1"
        output: "s1"
"""
    )
    return str(config)
