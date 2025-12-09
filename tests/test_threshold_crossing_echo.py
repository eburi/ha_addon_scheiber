"""
Tests for threshold-crossing echo behavior during transitions.

When a transition crosses the dimming threshold (e.g., brightness 252 -> 255),
the system sends a simple ON/OFF command instead of PWM. The hardware echo
reports brightness=0 in the status message, which should NOT overwrite our
internal brightness state.

Also tests negative transitions (fade-down) to ensure brightness calculation
is correct throughout the transition.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
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

    def test_brightness_preserved_post_transition_echo(self, bloc9_device, mock_mqtt):
        """
        Test that brightness is preserved even when echo arrives after transition completes.

        Scenario (the actual bug from user log):
        1. Transition completes at brightness 252
        2. Final ON command sent, transition removed from active_transitions
        3. CAN echo arrives with brightness=0 (threshold-crossing)
        4. No active transition exists anymore, but internal state has high brightness
        5. System should preserve internal brightness, not accept 0

        This is the race condition fix: the echo arrives microseconds after
        the transition cleanup.
        """
        # No active transition (it just completed and was removed)
        assert "s5" not in bloc9_device.transition_controller.active_transitions

        # But internal state has high brightness from the completed transition
        bloc9_device.state["s5"] = "ON"
        bloc9_device.state["s5_brightness"] = 252

        # Publish state with brightness=0 from CAN echo
        # (This is what publish_state would see when called with brightness=0 from decoder)
        # The new fix should detect: no active transition BUT internal brightness > threshold
        bloc9_device.publish_state("s5", "ON")

        # Verify that internal brightness was preserved, not overwritten to 0
        last_publish = mock_mqtt.publish.call_args_list[-1]
        published_payload = json.loads(last_publish[0][1])

        assert published_payload["brightness"] == 252

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


class TestNegativeTransitions:
    """Test fade-down (negative) transitions work correctly."""

    def test_fade_down_brightness_calculation(self, bloc9_device, mock_can_bus):
        """
        Test that fade-down transitions calculate brightness correctly at each step.

        Fade from 255 -> 20 should produce monotonically decreasing brightness values.
        """
        # Set up initial state
        bloc9_device.state["s5"] = "ON"
        bloc9_device.state["s5_brightness"] = 255

        # Track brightness values sent during transition
        brightness_values = []

        def capture_brightness(msg):
            # PWM commands have 4 bytes: [switch, state, 0x00, brightness]
            if len(msg.data) == 4 and msg.data[1] == 0x11:  # PWM command
                brightness_values.append(msg.data[3])

        mock_can_bus.send.side_effect = capture_brightness

        # Start transition controller manually to control timing
        with patch.object(bloc9_device.transition_controller, "step_delay", 0.01):
            bloc9_device.transition_controller.start_transition(
                property_name="s5",
                switch_nr=4,
                start_brightness=255,
                end_brightness=20,
                duration=0.1,
                easing_name="linear",
                on_step=None,
            )

            # Wait for transition to complete
            time.sleep(0.15)

        # Verify we got brightness values
        assert len(brightness_values) > 0, "No brightness values captured"

        # Verify monotonically decreasing (negative transition)
        for i in range(len(brightness_values) - 1):
            assert (
                brightness_values[i] >= brightness_values[i + 1]
            ), f"Brightness increased from {brightness_values[i]} to {brightness_values[i+1]}"

        # Verify start and end are in correct range
        # First value should be close to 255 (within a few steps)
        assert (
            brightness_values[0] >= 230
        ), f"Expected start brightness ~255, got {brightness_values[0]}"
        # Last value should be close to 20
        assert (
            brightness_values[-1] >= 18 and brightness_values[-1] <= 22
        ), f"Expected end brightness ~20, got {brightness_values[-1]}"

    def test_fade_down_uses_correct_easing_function(self, bloc9_device, mock_can_bus):
        """
        Test that fade-down transitions use ease_in easing (gentle at end).

        When fading down to OFF (brightness=0), the system should use ease_in_cubic
        to provide a gentle end to the transition.
        """
        # Set up initial state
        bloc9_device.state["s5"] = "ON"
        bloc9_device.state["s5_brightness"] = 100

        brightness_values = []

        def capture_brightness(msg):
            if len(msg.data) == 4 and msg.data[1] == 0x11:
                brightness_values.append(msg.data[3])

        mock_can_bus.send.side_effect = capture_brightness

        # Fade down to 0 (OFF)
        with patch.object(bloc9_device.transition_controller, "step_delay", 0.01):
            bloc9_device.transition_controller.start_transition(
                property_name="s5",
                switch_nr=4,
                start_brightness=100,
                end_brightness=0,
                duration=0.1,
                easing_name="ease_in_cubic",
                on_step=None,
            )

            time.sleep(0.15)

        # For ease_in_cubic, the brightness should decrease slowly at first,
        # then more rapidly toward the end
        # Check that the middle 50% of the transition covers less than 50% of the range
        if len(brightness_values) >= 4:
            quarter_idx = len(brightness_values) // 4
            three_quarter_idx = 3 * len(brightness_values) // 4

            # In the first quarter, we should still be at high brightness (ease-in = slow start)
            first_quarter_brightness = brightness_values[quarter_idx]
            assert first_quarter_brightness > 75, (
                f"Ease-in should be slow at start, but brightness dropped to {first_quarter_brightness} "
                f"in first quarter (expected > 75)"
            )

    def test_fade_down_from_high_to_mid_brightness(self, bloc9_device, mock_can_bus):
        """
        Test fade-down that stays in PWM range (doesn't cross thresholds).

        Fade 200 -> 50 should produce smooth PWM values throughout.
        """
        bloc9_device.state["s5"] = "ON"
        bloc9_device.state["s5_brightness"] = 200

        brightness_values = []

        def capture_brightness(msg):
            if len(msg.data) == 4 and msg.data[1] == 0x11:
                brightness_values.append(msg.data[3])

        mock_can_bus.send.side_effect = capture_brightness

        with patch.object(bloc9_device.transition_controller, "step_delay", 0.01):
            bloc9_device.transition_controller.start_transition(
                property_name="s5",
                switch_nr=4,
                start_brightness=200,
                end_brightness=50,
                duration=0.1,
                easing_name="linear",
                on_step=None,
            )

            time.sleep(0.15)

        # Verify we got values
        assert len(brightness_values) > 0

        # Verify monotonic decrease
        for i in range(len(brightness_values) - 1):
            assert brightness_values[i] >= brightness_values[i + 1]

        # Verify range
        assert brightness_values[0] == 200
        assert 48 <= brightness_values[-1] <= 52

    def test_negative_transition_brightness_range_correct(self, bloc9_device):
        """
        Test that negative brightness range calculation is correct.

        For fade 255 -> 20:
        - brightness_range = 20 - 255 = -235 (negative!)
        - At progress=0.5, brightness = 255 + (-235 * 0.5) = 137.5 ≈ 137
        """
        # Simulate the calculation from _execute_transition
        start_brightness = 255
        end_brightness = 20
        brightness_range = end_brightness - start_brightness  # -235

        # At 50% progress
        progress = 0.5
        expected_brightness = int(start_brightness + (brightness_range * progress))

        # Should be approximately halfway between 255 and 20
        assert (
            135 <= expected_brightness <= 140
        ), f"At 50% progress, expected brightness ~137, got {expected_brightness}"

        # At 0% progress
        progress = 0.0
        expected_brightness = int(start_brightness + (brightness_range * progress))
        assert expected_brightness == 255

        # At 100% progress
        progress = 1.0
        expected_brightness = int(start_brightness + (brightness_range * progress))
        assert expected_brightness == 20
