"""Tests for Switch class."""

import pytest
from unittest.mock import Mock, call
from scheiber.switch import Switch


class TestSwitch:
    """Test Switch basic ON/OFF control and observer pattern."""

    def test_initialization(self, mock_scheiber_can_bus, mock_logger):
        """Test switch initializes with correct parameters."""
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test Switch",
            entity_id="test_switch",
            can_bus=mock_scheiber_can_bus,
            logger=mock_logger,
        )

        assert switch.device_id == 3
        assert switch.switch_nr == 0
        assert switch.name == "Test Switch"
        assert switch.entity_id == "test_switch"
        assert switch.get_state() == False  # Default OFF

    def test_turn_on(self, mock_scheiber_can_bus):
        """Test turning switch ON sends correct CAN command."""
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            can_bus=mock_scheiber_can_bus,
        )

        switch.set(True)

        assert switch.get_state() == True
        mock_scheiber_can_bus.send_message.assert_called_once()

        # Verify CAN message structure
        call_args = mock_scheiber_can_bus.send_message.call_args
        arb_id, data = call_args[0]

        # Check data payload: [switch_nr, 0x01 for ON, 0x00, 0x00]
        assert data[0] == 0  # switch_nr
        assert data[1] == 0x01  # ON
        assert data[2] == 0x00
        assert data[3] == 0x00

    def test_turn_off(self, mock_scheiber_can_bus):
        """Test turning switch OFF sends correct CAN command."""
        switch = Switch(
            device_id=3,
            switch_nr=2,
            name="Test",
            entity_id="test",
            can_bus=mock_scheiber_can_bus,
        )

        # Turn on first
        switch.set(True)
        mock_scheiber_can_bus.send_message.reset_mock()

        # Now turn off
        switch.set(False)

        assert switch.get_state() == False
        mock_scheiber_can_bus.send_message.assert_called_once()

        # Verify CAN message
        call_args = mock_scheiber_can_bus.send_message.call_args
        arb_id, data = call_args[0]

        assert data[0] == 2  # switch_nr
        assert data[1] == 0x00  # OFF

    def test_observer_pattern(self, mock_scheiber_can_bus):
        """Test observer callbacks are triggered on state changes."""
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            can_bus=mock_scheiber_can_bus,
        )

        observer = Mock()
        switch.subscribe(observer)

        # Turn ON
        switch.set(True)
        observer.assert_called_with("state", True)

        # Turn OFF
        observer.reset_mock()
        switch.set(False)
        observer.assert_called_with("state", False)

    def test_multiple_observers(self, mock_scheiber_can_bus):
        """Test multiple observers all receive notifications."""
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            can_bus=mock_scheiber_can_bus,
        )

        observer1 = Mock()
        observer2 = Mock()

        switch.subscribe(observer1)
        switch.subscribe(observer2)

        switch.set(True)

        observer1.assert_called_with("state", True)
        observer2.assert_called_with("state", True)

    def test_unsubscribe(self, mock_scheiber_can_bus):
        """Test unsubscribing stops notifications."""
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            can_bus=mock_scheiber_can_bus,
        )

        observer = Mock()
        switch.subscribe(observer)
        switch.unsubscribe(observer)

        switch.set(True)

        observer.assert_not_called()

    def test_update_state_from_can(self, mock_scheiber_can_bus):
        """Test updating state from CAN bus (without sending command)."""
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            can_bus=mock_scheiber_can_bus,
        )

        observer = Mock()
        switch.subscribe(observer)

        # Simulate CAN message updating state
        switch.update_state(True)

        assert switch.get_state() == True
        observer.assert_called_with("state", True)
        # Should NOT send CAN message (only update internal state)
        mock_scheiber_can_bus.send_message.assert_not_called()

    def test_no_duplicate_notifications(self, mock_scheiber_can_bus):
        """Test setting same state doesn't trigger notification."""
        switch = Switch(
            device_id=3,
            switch_nr=0,
            name="Test",
            entity_id="test",
            can_bus=mock_scheiber_can_bus,
        )

        observer = Mock()
        switch.subscribe(observer)

        # Set to ON twice
        switch.set(True)
        observer.reset_mock()
        switch.set(True)

        # Should not notify second time (same state)
        observer.assert_not_called()
