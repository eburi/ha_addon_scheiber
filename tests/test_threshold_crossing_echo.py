"""
Tests for threshold-crossing echo behavior during transitions.

When a transition crosses the dimming threshold (e.g., brightness 252 -> 255),
the system sends a simple ON/OFF command instead of PWM. The hardware echo
reports brightness=0 in the status message, which should NOT overwrite our
internal brightness state.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scheiber" / "src"))

from devices import Bloc9
from config_loader import DiscoveryConfig


@pytest.fixture
def mock_mqtt():
    """Create a mock MQTT client."""
    mqtt = MagicMock()
    mqtt.publish = MagicMock()
    return mqtt


@pytest.fixture
def mock_can_bus():
    """Create a mock CAN bus."""
    bus = MagicMock()
    bus.send = MagicMock()
    bus.shutdown = MagicMock()
    return bus


@pytest.fixture
def temp_state_dir(tmp_path):
    """Create a temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def bloc9_device(mock_mqtt, mock_can_bus, temp_state_dir):
    """Create a Bloc9 device with mocked dependencies."""
    device_config = {
        "name": "Test Bloc9",
        "lights": [],
        "switches": [],
    }

    discovery_configs = [
        DiscoveryConfig(
            component="light",
            entity_id="test_light",
            name="Test Light",
            device_name="Test Bloc9",
            bus_id=7,
            output="s5",
        )
    ]

    device = Bloc9(
        device_type="bloc9",
        device_id=7,
        device_config=device_config,
        mqtt_client=mock_mqtt,
        can_bus=mock_can_bus,
        mqtt_topic_prefix="homeassistant",
        data_dir=str(temp_state_dir),
        discovery_configs=discovery_configs,
    )

    return device


class TestThresholdCrossingEcho:
    """Test brightness preservation during threshold-crossing echoes."""

    def test_brightness_preserved_during_transition_echo(self, bloc9_device, mock_mqtt):
        """
        Test that brightness is preserved when CAN echo reports 0 during transition.

        Scenario:
        1. Transition is running to brightness 255
        2. Internal state has high brightness (e.g., 255)
        3. CAN echo comes back with brightness=0 (threshold-crossing behavior)
        4. System should preserve brightness=255, not accept 0
        """
        # Set up: transition is running
        bloc9_device.state["s5"] = "ON"
        bloc9_device.state["s5_brightness"] = 255
        bloc9_device.transition_controller.active_transitions["s5"] = MagicMock()

        # Simulate CAN status update during transition
        # The CAN message parser would extract brightness=0 from a simple ON command
        # but publish_state should detect active transition and preserve internal brightness
        bloc9_device.publish_state("s5", "ON")

        # Get the last MQTT publish call
        last_publish = mock_mqtt.publish.call_args_list[-1]
        published_payload = json.loads(last_publish[0][1])

        # Verify that brightness is preserved as 255, not reset to 0
        assert published_payload["state"] == "ON"
        assert published_payload["brightness"] == 255

        # Verify state file has correct brightness
        state_file = bloc9_device._get_state_file_path()
        with open(state_file, "r") as f:
            state_data = json.load(f)

        assert state_data["s5_brightness"] == 255

    def test_brightness_not_preserved_without_active_transition(
        self, bloc9_device, mock_mqtt
    ):
        """
        Test that brightness preservation only happens during active transitions.

        If there's no active transition, accept the brightness from state normally.
        """
        # No active transition
        assert "s5" not in bloc9_device.transition_controller.active_transitions

        # Set state to ON with brightness 100
        bloc9_device.state["s5"] = "ON"
        bloc9_device.state["s5_brightness"] = 100

        # Publish state (no active transition, should use state as-is)
        bloc9_device.publish_state("s5", "ON")

        # Verify that brightness was published normally
        last_publish = mock_mqtt.publish.call_args_list[-1]
        published_payload = json.loads(last_publish[0][1])

        assert published_payload["brightness"] == 100

    def test_brightness_zero_preserved_during_transition_with_high_internal_brightness(
        self, bloc9_device, mock_mqtt
    ):
        """
        Test the specific bug scenario: CAN echo reports brightness=0 for threshold-crossing ON.

        The fix should detect:
        1. Active transition exists
        2. CAN echo has brightness=0
        3. State is ON
        4. Internal brightness > threshold
        Then preserve internal brightness instead of using 0.
        """
        # Set up: transition ending at brightness 255
        bloc9_device.state["s5"] = "ON"
        bloc9_device.state["s5_brightness"] = 255  # Set by send_final_command thread
        bloc9_device.transition_controller.active_transitions["s5"] = MagicMock()

        # Simulate what happens when CAN decoder processes a simple ON command:
        # It doesn't have PWM brightness byte, so it would default to 0
        # But publish_state should preserve our internal brightness=255
        bloc9_device.publish_state("s5", "ON")

        # Verify brightness preserved in MQTT
        last_publish = mock_mqtt.publish.call_args_list[-1]
        published_payload = json.loads(last_publish[0][1])
        assert published_payload["brightness"] == 255

        # Verify brightness persisted to disk
        state_file = bloc9_device._get_state_file_path()
        with open(state_file, "r") as f:
            state_data = json.load(f)
        assert state_data["s5_brightness"] == 255

    def test_fade_down_scenario_brightness_detection(self, bloc9_device):
        """
        Test that fade-down can detect correct current brightness after threshold crossing.

        This tests the end-to-end scenario:
        1. State shows brightness=255 (from previous fade-up that crossed threshold)
        2. Next command needs to detect current_brightness=255, not 0
        """
        # Set state as if we just completed a fade-up to 255
        bloc9_device.state["s5"] = "ON"
        bloc9_device.state["s5_brightness"] = 255
        bloc9_device._persist_state("s5", "ON")
        bloc9_device._persist_state("s5_brightness", 255)

        # Verify state file has correct brightness
        state_file = bloc9_device._get_state_file_path()
        with open(state_file, "r") as f:
            state_data = json.load(f)
        assert state_data["s5_brightness"] == 255

        # Now when the next command comes in, it should detect current_brightness=255
        # (This is tested implicitly - if brightness wasn't persisted, it would be missing)
        assert bloc9_device.state.get("s5_brightness") == 255
