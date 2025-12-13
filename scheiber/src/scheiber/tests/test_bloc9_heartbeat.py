"""
Test Bloc9 heartbeat (status message) behavior.

Verifies that low-priority status messages (0x00000600) are treated as
heartbeats only and do NOT update switch/light states.
"""

from unittest.mock import Mock, call, MagicMock
import pytest
import can
from scheiber.bloc9 import Bloc9Device
from scheiber.matchers import Matcher


class TestBloc9Heartbeat:
    """Test Bloc9 heartbeat message handling."""

    def test_heartbeat_does_not_update_light_state(self):
        """Test that heartbeat messages don't override light states."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Main Light", "entity_id": "main_light"}},
        )

        light = device.lights[0]
        observer = Mock()
        light.subscribe(observer)

        # Set light to brightness 76
        light.set_brightness(76)
        observer.reset_mock()

        # Simulate heartbeat with stale data (OFF state)
        # Data format: [s1_state, s1_brightness, s2_state, s2_brightness, s3_state, s3_brightness]
        heartbeat_msg = can.Message(
            arbitration_id=0x000006B8,  # 0x00000600 | ((7 << 3) | 0x80)
            data=bytes([0x08, 0x11, 0x00, 0x4A, 0x0C]),
            is_extended_id=True,
        )

        device.process_message(heartbeat_msg)

        # Verify light state wasn't changed
        assert light.get_state() == {
            "state": True,
            "brightness": 76,
        }, "Light state should not be affected by heartbeat"
        observer.assert_not_called()  # No state change notification

    def test_heartbeat_publishes_device_info(self):
        """Test that heartbeat triggers device info publication."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={
                "s1": {"name": "Light 1", "entity_id": "light_1"},
                "s5": {"name": "Main Light", "entity_id": "main_light"},
            },
            switches_config={"s3": {"name": "Switch 3", "entity_id": "switch_3"}},
        )

        # Subscribe device-level observer
        device_observer = Mock()
        device.subscribe(device_observer)

        # Simulate heartbeat
        heartbeat_msg = can.Message(
            arbitration_id=0x000006B8,
            data=bytes([0x08, 0x11, 0x00, 0x4A, 0x0C]),
            is_extended_id=True,
        )

        device.process_message(heartbeat_msg)

        # Verify device observer was notified with device info
        device_observer.assert_called_once()
        args = device_observer.call_args[0]
        call_dict = args[0]
        assert "device_info" in call_dict

        device_info = call_dict["device_info"]
        assert device_info["device_type"] == "bloc9"
        assert device_info["bus_id"] == 7
        assert "outputs" in device_info
        assert device_info["outputs"]["s1"] == "Light 1"
        assert device_info["outputs"]["s3"] == "Switch 3"
        assert device_info["outputs"]["s5"] == "Main Light"

    def test_state_change_message_still_updates_state(self):
        """Test that actual state change messages (not heartbeats) do update state."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Main Light", "entity_id": "main_light"}},
        )

        light = device.lights[0]
        observer = Mock()
        light.subscribe(observer)

        # Set initial state
        light.set_brightness(100)
        observer.reset_mock()

        # Simulate S5/S6 change message (0x021A0600)
        # Format: 8 bytes [s5_brightness, 0, 0, s5_state_bit, s6_brightness, 0, 0, s6_state_bit]
        change_msg = can.Message(
            arbitration_id=0x021A06B8,  # 0x021A0600 | ((7 << 3) | 0x80)
            data=bytes(
                [0x4C, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]
            ),  # S5: brightness=76 ON, S6: OFF
            is_extended_id=True,
        )

        device.process_message(change_msg)

        # Verify light state WAS updated from change message
        assert light.get_state() == {
            "state": True,
            "brightness": 76,
        }, "Light should update from change message"
        observer.assert_called_once()  # State change notification sent

    def test_heartbeat_after_command_does_not_reset(self):
        """Test the specific bug scenario: command followed immediately by heartbeat."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Main Light", "entity_id": "main_light"}},
        )

        light = device.lights[0]

        # Initial state: OFF
        assert light.get_state() == {"state": False, "brightness": 0}

        # Step 1: Send brightness command (brightness=76)
        light.set_brightness(76)
        assert light.get_state() == {"state": True, "brightness": 76}

        # Step 2: Heartbeat arrives 22ms later with old stale data (OFF)
        # This is the actual message from the user's log
        heartbeat_msg = can.Message(
            arbitration_id=0x000006B8,
            data=bytes([0x08, 0x11, 0x00, 0x4A, 0x0C]),
            is_extended_id=True,
        )

        device.process_message(heartbeat_msg)

        # Step 3: Verify light state is STILL brightness=76 (not reset by heartbeat)
        assert light.get_state() == {
            "state": True,
            "brightness": 76,
        }, "Heartbeat should not override command"

    def test_heartbeat_with_no_configured_outputs(self):
        """Test heartbeat handling when no outputs are configured."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(device_id=7, can_bus=mock_bus)

        device_observer = Mock()
        device.subscribe(device_observer)

        # Simulate heartbeat
        heartbeat_msg = can.Message(
            arbitration_id=0x000006B8,
            data=bytes([0x00, 0x00, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )

        # Should not crash, should still publish device info
        device.process_message(heartbeat_msg)

        device_observer.assert_called_once()
        args = device_observer.call_args[0]
        call_dict = args[0]
        assert "device_info" in call_dict

        device_info = call_dict["device_info"]
        # All outputs should be "unknown"
        for i in range(1, 7):
            assert device_info["outputs"][f"s{i}"] == "unknown"

    def test_multiple_heartbeats_in_sequence(self):
        """Test that multiple heartbeats don't affect state."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={
                "s1": {"name": "Light 1", "entity_id": "light_1"},
                "s5": {"name": "Main Light", "entity_id": "main_light"},
            },
        )

        light1 = device.lights[0]  # S1
        light5 = device.lights[1]  # S5

        # Set states
        light1.set_brightness(128)
        light5.set_brightness(200)

        observer1 = Mock()
        observer5 = Mock()
        light1.subscribe(observer1)
        light5.subscribe(observer5)

        # Send multiple heartbeats with varying data
        for i in range(5):
            heartbeat_msg = can.Message(
                arbitration_id=0x000006B8,
                data=bytes([i, i * 10, i * 20, i * 30, i * 40]),
                is_extended_id=True,
            )
            device.process_message(heartbeat_msg)

        # Verify states unchanged
        assert light1.get_state() == {"state": True, "brightness": 128}
        assert light5.get_state() == {"state": True, "brightness": 200}
        observer1.assert_not_called()
        observer5.assert_not_called()

    def test_switch_not_affected_by_heartbeat(self):
        """Test that switches are also not affected by heartbeat messages."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            switches_config={"s3": {"name": "Switch 3", "entity_id": "switch_3"}},
        )

        switch = device.switches[0]
        observer = Mock()
        switch.subscribe(observer)

        # Turn switch ON
        switch.set(True)
        assert switch.get_state() == True
        observer.reset_mock()

        # Heartbeat with S3 showing OFF (byte 4 = 0x00)
        heartbeat_msg = can.Message(
            arbitration_id=0x000006B8,
            data=bytes([0x01, 0xFF, 0x01, 0xFF, 0x00, 0x00]),  # S3 appears OFF
            is_extended_id=True,
        )

        device.process_message(heartbeat_msg)

        # Verify switch state unchanged
        assert switch.get_state() == True
        observer.assert_not_called()

    def test_device_observer_pattern_for_heartbeat(self):
        """Test that device-level observer pattern works correctly."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s1": {"name": "Light", "entity_id": "light"}},
        )

        # Multiple observers
        observer1 = Mock()
        observer2 = Mock()
        device.subscribe(observer1)
        device.subscribe(observer2)

        # Send heartbeat
        heartbeat_msg = can.Message(
            arbitration_id=0x000006B8,
            data=bytes([0x01, 0xFF, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )

        device.process_message(heartbeat_msg)

        # Both observers notified
        observer1.assert_called_once()
        observer2.assert_called_once()

        # Unsubscribe one
        device.unsubscribe(observer1)
        observer1.reset_mock()
        observer2.reset_mock()

        device.process_message(heartbeat_msg)

        # Only observer2 notified
        observer1.assert_not_called()
        observer2.assert_called_once()
