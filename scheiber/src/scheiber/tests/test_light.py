"""Tests for DimmableLight class."""

import pytest
import time
from unittest.mock import Mock, call
from scheiber.light import DimmableLight


class TestDimmableLight:
    """Test DimmableLight brightness control, transitions, and flash effects."""

    def test_initialization(self, mock_logger):
        """Test light initializes with correct parameters."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test Light",
            entity_id="test_light",
            send_command_func=send_func,
            logger=mock_logger,
        )

        assert light.device_id == 3
        assert light.switch_nr == 0
        assert light.name == "Test Light"
        assert light.entity_id == "test_light"
        assert light.get_brightness() == 0
        assert light.is_on() == False

    def test_set_brightness_on(self):
        """Test setting brightness turns light ON."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        light.set_brightness(200)

        assert light.get_brightness() == 200
        assert light.is_on() == True
        send_func.assert_called_once()

    def test_set_brightness_off(self):
        """Test setting brightness to 0 turns light OFF."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        light.set_brightness(200)
        send_func.reset_mock()

        light.set_brightness(0)

        assert light.get_brightness() == 0
        assert light.is_on() == False
        send_func.assert_called_once()

    def test_observer_notifications(self):
        """Test observer callbacks for brightness and state changes."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        observer = Mock()
        light.subscribe(observer)

        light.set_brightness(200)

        # Should receive both state and brightness notifications
        assert observer.call_count == 2
        calls = observer.call_args_list
        assert call("state", True) in calls
        assert call("brightness", 200) in calls

    def test_fade_to(self):
        """Test fade transition starts and reaches target."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        # Start at brightness 0
        light.set_brightness(0)
        send_func.reset_mock()

        # Fade to 255 over 100ms
        light.fade_to(255, duration_ms=100)

        # Transition should be active
        assert light.transition_controller.is_active()

        # Wait for transition to complete (with margin)
        time.sleep(0.15)

        # Should have reached target
        assert light.get_brightness() == 255
        assert not light.transition_controller.is_active()

        # Should have sent multiple commands during transition
        assert send_func.call_count > 1

    def test_transition_cancellation(self):
        """Test setting brightness cancels active transition."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        # Start fade
        light.fade_to(255, duration_ms=500)
        assert light.transition_controller.is_active()

        # Cancel by setting brightness directly
        light.set_brightness(100)

        # Transition should be cancelled
        assert not light.transition_controller.is_active()
        assert light.get_brightness() == 100

    def test_flash_effect(self):
        """Test flash effect restores previous state."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        # Set initial brightness
        light.set_brightness(100)
        send_func.reset_mock()

        # Flash (should go to 255 briefly then back to 100)
        light.flash(count=1, duration_ms=50)

        # Wait for flash to complete
        time.sleep(0.15)

        # Should be back to original brightness
        assert light.get_brightness() == 100

        # Should have sent commands (flash ON + restore)
        assert send_func.call_count >= 2

    def test_flash_from_off(self):
        """Test flash works when light is OFF."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        # Start with light OFF
        assert light.is_on() == False

        # Flash
        light.flash(count=1, duration_ms=50)

        # Wait
        time.sleep(0.15)

        # Should be back OFF
        assert light.is_on() == False
        assert light.get_brightness() == 0

    def test_cancel_method(self):
        """Test cancel() stops transitions and flash."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        # Start transition
        light.fade_to(255, duration_ms=500)
        assert light.transition_controller.is_active()

        # Cancel
        light.cancel()

        # Should be cancelled
        assert not light.transition_controller.is_active()
        assert not light.flash_controller.is_active()

    def test_update_state_from_can(self):
        """Test updating state from CAN bus without sending command."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        observer = Mock()
        light.subscribe(observer)

        # Simulate CAN message updating state
        light.update_state(True, 150)

        assert light.is_on() == True
        assert light.get_brightness() == 150

        # Should notify observers
        assert observer.call_count >= 2

        # Should NOT send CAN command
        send_func.assert_not_called()

    def test_dimming_threshold_off(self):
        """Test brightness 0-2 is treated as OFF."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        light.set_brightness(2)
        assert light.is_on() == False

        light.set_brightness(3)
        assert light.is_on() == True

    def test_dimming_threshold_full_on(self):
        """Test brightness 253-255 is full ON."""
        send_func = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_func,
        )

        light.set_brightness(253)
        assert light.is_on() == True

        light.set_brightness(255)
        assert light.is_on() == True
