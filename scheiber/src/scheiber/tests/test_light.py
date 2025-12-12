"""Tests for DimmableLight class."""

import pytest
from unittest.mock import Mock, call
from scheiber.light import DimmableLight


class TestDimmableLight:
    """Test DimmableLight brightness control and observer pattern."""

    def test_initialization(self, mock_logger):
        """Test light initializes with correct parameters."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test Light",
            entity_id="test_light",
            send_command_func=send_command_mock,
            logger=mock_logger,
        )

        assert light.device_id == 3
        assert light.switch_nr == 0
        assert light.name == "Test Light"
        assert light.entity_id == "test_light"
        assert light._state == False
        assert light._brightness == 0

    def test_set_brightness(self):
        """Test setting brightness sends CAN command."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=2,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        # Set brightness to 128
        light.set_brightness(128)
        assert light._brightness == 128
        assert light._state == True
        send_command_mock.assert_called_once_with(2, True, 128)

        # Set brightness to 0 (OFF)
        send_command_mock.reset_mock()
        light.set_brightness(0)
        assert light._brightness == 0
        assert light._state == False
        send_command_mock.assert_called_once_with(2, False, 0)

        # Set brightness to 255 (full ON)
        send_command_mock.reset_mock()
        light.set_brightness(255)
        assert light._brightness == 255
        assert light._state == True
        send_command_mock.assert_called_once_with(2, True, 255)

    def test_brightness_clamping(self):
        """Test brightness is clamped to 0-255 range."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        # Below minimum
        light.set_brightness(-10)
        assert light._brightness == 0

        # Above maximum
        light.set_brightness(300)
        assert light._brightness == 255

    def test_observer_pattern(self):
        """Test observer callbacks are triggered on state/brightness changes."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        observer = Mock()
        light.subscribe(observer)

        # Set brightness
        light.set_brightness(100)

        # Should notify once with state dict
        observer.assert_called_once_with({"state": True, "brightness": 100})

    def test_multiple_observers(self):
        """Test multiple observers all receive notifications."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        observer1 = Mock()
        observer2 = Mock()

        light.subscribe(observer1)
        light.subscribe(observer2)

        light.set_brightness(150)

        # Both observers should be called once with state dict
        observer1.assert_called_once_with({"state": True, "brightness": 150})
        observer2.assert_called_once_with({"state": True, "brightness": 150})

    def test_unsubscribe(self):
        """Test unsubscribing stops notifications."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        observer = Mock()
        light.subscribe(observer)
        light.unsubscribe(observer)

        light.set_brightness(100)

        observer.assert_not_called()

    def test_update_state_from_can(self):
        """Test updating state from CAN bus (without sending command)."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        observer = Mock()
        light.subscribe(observer)

        # Simulate CAN message updating state
        light.update_state(state=True, brightness=200)

        assert light._state == True
        assert light._brightness == 200
        observer.assert_called_once_with({"state": True, "brightness": 200})
        # Should NOT send CAN command (only update internal state)
        send_command_mock.assert_not_called()

    def test_update_state_bloc9_quirk_translation(self):
        """Test Bloc9 hardware quirk translation (state=ON, brightness=0 -> brightness=255)."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        observer = Mock()
        light.subscribe(observer)

        # Bloc9 reports: state=ON, brightness=0 (full ON without PWM)
        # Should translate to: state=ON, brightness=255
        light.update_state(state=True, brightness=0)

        assert light._state == True
        assert light._brightness == 255  # Translated!
        observer.assert_called_once_with({"state": True, "brightness": 255})
        # Should NOT send CAN command
        send_command_mock.assert_not_called()

    def test_update_state_no_quirk_for_normal_brightness(self):
        """Test that normal brightness values are NOT translated."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        observer = Mock()
        light.subscribe(observer)

        # Normal PWM brightness (not the quirk case)
        light.update_state(state=True, brightness=128)

        assert light._state == True
        assert light._brightness == 128  # NOT translated
        observer.assert_called_once_with({"state": True, "brightness": 128})

    def test_update_state_off_with_zero_brightness(self):
        """Test that OFF state with brightness=0 stays as OFF and doesn't trigger quirk."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        # Set light to ON first
        light.set_brightness(100)

        observer = Mock()
        light.subscribe(observer)

        # OFF state with brightness=0 should NOT trigger quirk translation
        light.update_state(state=False, brightness=0)

        assert light._state == False
        assert light._brightness == 0  # NOT translated (OFF is OFF)
        observer.assert_called_once_with({"state": False, "brightness": 0})

    def test_get_state(self):
        """Test get_state returns current state and brightness."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        # Initial state
        state = light.get_state()
        assert state == {"state": False, "brightness": 0}

        # After setting brightness
        light.set_brightness(180)
        state = light.get_state()
        assert state == {"state": True, "brightness": 180}

    def test_set_with_state_and_brightness(self):
        """Test set() with explicit state and brightness."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        # Turn ON with brightness
        light.set(state=True, brightness=200)
        assert light._state == True
        assert light._brightness == 200
        send_command_mock.assert_called_with(0, True, 200)

        # Turn OFF
        send_command_mock.reset_mock()
        light.set(state=False, brightness=0)
        assert light._state == False
        assert light._brightness == 0
        send_command_mock.assert_called_with(0, False, 0)

    def test_set_on_without_brightness_uses_previous(self):
        """Test set(state=True) without brightness uses previous brightness."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        # Set initial brightness
        light.set_brightness(150)
        send_command_mock.reset_mock()

        # Turn OFF
        light.set(state=False)
        assert light._brightness == 0

        # Turn ON again (should restore previous brightness)
        send_command_mock.reset_mock()
        light.set(state=True)
        # Should use default 255 since previous was 0
        assert light._brightness == 255
        send_command_mock.assert_called_with(0, True, 255)

    def test_update_state_no_notification_when_unchanged(self):
        """Test that update_state doesn't notify observers if state unchanged."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        # Set initial state
        light.set_brightness(100)

        observer = Mock()
        light.subscribe(observer)

        # Update with same state
        light.update_state(state=True, brightness=100)

        # Observer should NOT be called (no change)
        observer.assert_not_called()

    def test_string_representation(self):
        """Test string representation."""
        send_command_mock = Mock()
        light = DimmableLight(
            device_id=3,
            switch_nr=0,
            name="Living Room",
            entity_id="living_room",
            send_command_func=send_command_mock,
        )

        # OFF state
        assert str(light) == "DimmableLight(Living Room, state=OFF, brightness=0)"

        # ON state
        light.set_brightness(180)
        assert str(light) == "DimmableLight(Living Room, state=ON, brightness=180)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
