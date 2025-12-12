"""Tests for Switch class."""

import pytest
from unittest.mock import Mock, call
from scheiber.switch import Switch


class TestSwitch:
    """Test Switch basic ON/OFF control and observer pattern."""

    def test_initialization(self, mock_scheiber_can_bus, mock_logger):
        """Test switch initializes with correct parameters."""
        send_command_mock = Mock()
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test Switch",
            entity_id="test_switch",
            send_command_func=send_command_mock,
            logger=mock_logger,
        )

        assert switch.device_id == 3
        assert switch.switch_nr == 0
        assert switch.name == "Test Switch"
        assert switch.entity_id == "test_switch"
        assert switch.get_state() == False  # Default OFF

    def test_observer_pattern(self, mock_scheiber_can_bus):
        """Test observer callbacks are triggered on state changes."""
        send_command_mock = Mock()
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        observer = Mock()
        switch.subscribe(observer)

        # Turn ON
        switch.set(True)
        observer.assert_called_with({"state": True})

        # Turn OFF
        observer.reset_mock()
        switch.set(False)
        observer.assert_called_with({"state": False})

    def test_multiple_observers(self, mock_scheiber_can_bus):
        """Test multiple observers all receive notifications."""
        send_command_mock = Mock()
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        observer1 = Mock()
        observer2 = Mock()

        switch.subscribe(observer1)
        switch.subscribe(observer2)

        switch.set(True)

        observer1.assert_called_with({"state": True})
        observer2.assert_called_with({"state": True})

    def test_unsubscribe(self, mock_scheiber_can_bus):
        """Test unsubscribing stops notifications."""
        send_command_mock = Mock()
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        observer = Mock()
        switch.subscribe(observer)
        switch.unsubscribe(observer)

        switch.set(True)

        observer.assert_not_called()

    def test_update_state_from_can(self, mock_scheiber_can_bus):
        """Test updating state from CAN bus (without sending command)."""
        send_command_mock = Mock()
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        observer = Mock()
        switch.subscribe(observer)

        # Simulate CAN message updating state
        switch.update_state(True)

        assert switch.get_state() == True
        observer.assert_called_with({"state": True})
        # Should NOT send CAN command (only update internal state)
        send_command_mock.assert_not_called()

    def test_set_sends_command_without_brightness(self, mock_scheiber_can_bus):
        """Test that set() sends CAN command with only switch_nr and state."""
        send_command_mock = Mock()
        switch = Switch(
            device_id=3,
            switch_nr=2,
            name="Test",
            entity_id="test",
            send_command_func=send_command_mock,
        )

        # Turn ON
        switch.set(True)
        send_command_mock.assert_called_once_with(2, True)

        # Turn OFF
        send_command_mock.reset_mock()
        switch.set(False)
        send_command_mock.assert_called_once_with(2, False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
