#!/usr/bin/env python3
"""
Test dimming threshold behavior for Bloc9 devices.

Tests edge cases where brightness values near 0 or 255 should snap to
full OFF or full ON states, and verifies that transitions near these
edges don't get incorrectly cancelled due to expected value mismatches.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scheiber" / "src"))

from devices import Bloc9


class TestDimmingThreshold(unittest.TestCase):
    """Test dimming threshold edge case handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.mqtt_client = Mock()
        self.can_bus = Mock()

        # Mock device configuration
        self.device_config = {
            "name": "Test Bloc9",
            "matchers": [{"properties": {"s1": {}, "s1_brightness": {}}}],
        }

        # Mock discovery configs
        self.discovery_configs = [
            Mock(
                output="s1",
                component="light",
                entity_id="test_light",
                name="Test Light",
            )
        ]

        # Create Bloc9 instance
        self.device = Bloc9(
            device_type="bloc9",
            device_id=10,
            device_config=self.device_config,
            mqtt_client=self.mqtt_client,
            mqtt_topic_prefix="homeassistant",
            can_bus=self.can_bus,
            data_dir="/tmp/test_data",
            discovery_configs=self.discovery_configs,
        )

    def test_default_dimming_threshold(self):
        """Test that default dimming threshold is set correctly."""
        self.assertEqual(self.device.dimming_threshold, 2)

    def test_brightness_zero_sends_off(self):
        """Test that brightness=0 sends OFF command."""
        self.device._send_switch_command(0, True, brightness=0)

        # Verify CAN message sent
        self.can_bus.send.assert_called_once()
        msg = self.can_bus.send.call_args[0][0]

        # Should send OFF command: [switch_nr, 0x00, 0x00, 0x00]
        self.assertEqual(msg.data[0], 0)  # switch_nr
        self.assertEqual(msg.data[1], 0x00)  # OFF byte
        self.assertEqual(msg.data[2], 0x00)
        self.assertEqual(msg.data[3], 0x00)

    def test_brightness_within_threshold_sends_off(self):
        """Test that brightness <= threshold sends OFF command."""
        for brightness in [0, 1, 2]:
            self.can_bus.reset_mock()
            self.device._send_switch_command(0, True, brightness=brightness)

            # Verify CAN message sent
            self.can_bus.send.assert_called_once()
            msg = self.can_bus.send.call_args[0][0]

            # Should send OFF command
            self.assertEqual(
                msg.data[1], 0x00, f"brightness={brightness} should send OFF"
            )

    def test_brightness_255_sends_on(self):
        """Test that brightness=255 sends ON command (no PWM)."""
        self.device._send_switch_command(0, True, brightness=255)

        # Verify CAN message sent
        self.can_bus.send.assert_called_once()
        msg = self.can_bus.send.call_args[0][0]

        # Should send ON command: [switch_nr, 0x01, 0x00, 0x00]
        self.assertEqual(msg.data[0], 0)  # switch_nr
        self.assertEqual(msg.data[1], 0x01)  # ON byte
        self.assertEqual(msg.data[2], 0x00)
        self.assertEqual(msg.data[3], 0x00)

    def test_brightness_near_255_sends_on(self):
        """Test that brightness >= (255-threshold) sends ON command."""
        for brightness in [253, 254, 255]:
            self.can_bus.reset_mock()
            self.device._send_switch_command(0, True, brightness=brightness)

            # Verify CAN message sent
            self.can_bus.send.assert_called_once()
            msg = self.can_bus.send.call_args[0][0]

            # Should send ON command (no PWM)
            self.assertEqual(
                msg.data[1], 0x01, f"brightness={brightness} should send ON"
            )
            self.assertEqual(
                msg.data[3], 0x00, f"brightness={brightness} should not use PWM"
            )

    def test_brightness_middle_range_sends_pwm(self):
        """Test that middle range brightness values send PWM command."""
        for brightness in [3, 50, 128, 200, 252]:
            self.can_bus.reset_mock()
            self.device._send_switch_command(0, True, brightness=brightness)

            # Verify CAN message sent
            self.can_bus.send.assert_called_once()
            msg = self.can_bus.send.call_args[0][0]

            # Should send PWM command: [switch_nr, 0x11, 0x00, brightness]
            self.assertEqual(msg.data[0], 0, f"brightness={brightness} switch_nr")
            self.assertEqual(
                msg.data[1], 0x11, f"brightness={brightness} should send PWM command"
            )
            self.assertEqual(msg.data[2], 0x00, f"brightness={brightness} byte 2")
            self.assertEqual(
                msg.data[3], brightness, f"brightness={brightness} should be in byte 3"
            )

    def test_transition_to_255_not_cancelled_by_echo(self):
        """Test that transition to 255 doesn't get cancelled by ON state echo."""
        # Set up initial state
        self.device.state["s1"] = "ON"
        self.device.state["s1_brightness"] = 250

        # Start a transition (simulate)
        self.device.transition_controller.active_transitions["s1"] = Mock()

        # Simulate CAN bus echo: when we send brightness=255,
        # CAN bus reports state=ON (not brightness value)
        # This should NOT cancel the transition

        # Call publish_state with the echo
        self.device.publish_state("s1", 1)  # 1 = ON

        # Transition should still be active (not cancelled)
        self.assertIn("s1", self.device.transition_controller.active_transitions)

    def test_transition_to_0_not_cancelled_by_echo(self):
        """Test that transition to 0 doesn't get cancelled by OFF state echo."""
        # Set up initial state: transitioning towards 0
        # Brightness at 2 (at threshold) should result in OFF state
        self.device.state["s1"] = "OFF"
        self.device.state["s1_brightness"] = 2  # At threshold, expects OFF

        # Start a transition (simulate)
        self.device.transition_controller.active_transitions["s1"] = Mock()

        # Simulate CAN bus echo: when we send brightness=0-2,
        # CAN bus reports state=OFF
        # This should NOT cancel the transition

        # Call publish_state with the echo
        self.device.publish_state("s1", 0)  # 0 = OFF

        # Transition should still be active (not cancelled)
        self.assertIn("s1", self.device.transition_controller.active_transitions)

    def test_external_override_cancels_transition(self):
        """Test that actual external state change cancels transition."""
        # Set up initial state: device thinks it's ON
        self.device.state["s1"] = "ON"
        self.device.state["s1_brightness"] = 128

        # Start a transition (simulate)
        self.device.transition_controller.active_transitions["s1"] = Mock()

        # Simulate external override: CAN bus reports OFF when we expect ON
        # This SHOULD cancel the transition

        # Call publish_state with unexpected state
        self.device.publish_state("s1", 0)  # 0 = OFF, but we expected ON

        # Transition should be cancelled
        self.assertNotIn("s1", self.device.transition_controller.active_transitions)

    def test_threshold_boundaries(self):
        """Test exact threshold boundary values."""
        threshold = self.device.dimming_threshold

        # Test lower boundary: threshold should send OFF
        self.can_bus.reset_mock()
        self.device._send_switch_command(0, True, brightness=threshold)
        msg = self.can_bus.send.call_args[0][0]
        self.assertEqual(msg.data[1], 0x00, f"brightness={threshold} should send OFF")

        # Test lower boundary + 1: should send PWM
        self.can_bus.reset_mock()
        self.device._send_switch_command(0, True, brightness=threshold + 1)
        msg = self.can_bus.send.call_args[0][0]
        self.assertEqual(
            msg.data[1], 0x11, f"brightness={threshold + 1} should send PWM"
        )

        # Test upper boundary: (255 - threshold) should send ON
        self.can_bus.reset_mock()
        self.device._send_switch_command(0, True, brightness=255 - threshold)
        msg = self.can_bus.send.call_args[0][0]
        self.assertEqual(
            msg.data[1], 0x01, f"brightness={255 - threshold} should send ON"
        )

        # Test upper boundary - 1: should send PWM
        self.can_bus.reset_mock()
        self.device._send_switch_command(0, True, brightness=255 - threshold - 1)
        msg = self.can_bus.send.call_args[0][0]
        self.assertEqual(
            msg.data[1], 0x11, f"brightness={255 - threshold - 1} should send PWM"
        )

    def test_transition_near_upper_threshold_not_cancelled(self):
        """Test that transition near 255 doesn't get falsely cancelled."""
        # Set up state during transition to 255
        # At brightness 252, we're in PWM mode, expecting ON
        self.device.state["s1"] = "ON"
        self.device.state["s1_brightness"] = 252

        # Start a transition
        self.device.transition_controller.active_transitions["s1"] = Mock()

        # CAN bus echoes ON state
        self.device.publish_state("s1", 1)  # 1 = ON

        # Should NOT cancel (brightness 252 expects ON state)
        self.assertIn("s1", self.device.transition_controller.active_transitions)

    def test_transition_crosses_threshold_to_off(self):
        """Test transition from PWM to OFF doesn't get cancelled."""
        # Currently at brightness 3 (just above threshold), in PWM mode
        self.device.state["s1"] = "ON"  # PWM mode shows as ON
        self.device.state["s1_brightness"] = 3

        # Start a transition
        self.device.transition_controller.active_transitions["s1"] = Mock()

        # Transition steps to brightness 2 (at threshold) -> state becomes OFF
        # Update internal state to reflect this
        self.device.state["s1_brightness"] = 2

        # CAN bus echoes OFF state
        self.device.publish_state("s1", 0)  # 0 = OFF

        # Should NOT cancel (brightness 2 expects OFF state)
        self.assertIn("s1", self.device.transition_controller.active_transitions)

    def test_transition_crosses_threshold_to_on(self):
        """Test transition from OFF to PWM doesn't get cancelled."""
        # Currently at brightness 2 (at threshold), OFF
        self.device.state["s1"] = "OFF"
        self.device.state["s1_brightness"] = 2

        # Start a transition
        self.device.transition_controller.active_transitions["s1"] = Mock()

        # Transition steps to brightness 3 (above threshold) -> state becomes ON
        # Update internal state to reflect this
        self.device.state["s1_brightness"] = 3

        # CAN bus echoes ON state
        self.device.publish_state("s1", 1)  # 1 = ON

        # Should NOT cancel (brightness 3 expects ON state)
        self.assertIn("s1", self.device.transition_controller.active_transitions)


if __name__ == "__main__":
    unittest.main()
