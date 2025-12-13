"""
Test that CAN messages are correctly routed to the right device.

This test verifies the critical bug fix where messages from one device
should not affect other devices (no cross-device side effects).

Related to the bug: "Switches don't work and they have side effects!"
where a switch on device 10 was affecting ALL Bloc9 devices (1-10).

The fix: Changed matcher mask from 0xFFFFFF00 to 0xFFFFFFFF to include
the device ID byte in the matching.
"""

import pytest
import can
from unittest.mock import Mock
from scheiber.bloc9 import Bloc9Device


class TestMessageRouting:
    """Test that CAN messages route to correct devices only."""

    def test_message_only_affects_target_device(self):
        """
        Test that a message for device 7 doesn't affect device 8.

        This was the critical bug: message 0x021806D0 (device 10, S3/S4)
        was matching ALL devices because mask was 0xFFFFFF00.
        """
        mock_bus = Mock()

        # Create two devices
        device_7 = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={
                "s5": {"name": "Light Device 7 S5"},
            },
        )

        device_8 = Bloc9Device(
            device_id=8,
            can_bus=mock_bus,
            lights_config={
                "s5": {"name": "Light Device 8 S5"},
            },
        )

        # Message for device 7 S5/S6: S5 ON with brightness 100
        msg_device_7 = can.Message(
            arbitration_id=0x021A06B8,  # Device 7, S5/S6
            data=bytes([0x64, 0x00, 0x11, 0x01, 0x00, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )

        # Process message on both devices
        device_7.process_message(msg_device_7)
        device_8.process_message(msg_device_7)

        # Verify device 7 was affected
        d7_state = device_7.lights[0].get_state()
        assert d7_state["state"] == True
        assert d7_state["brightness"] == 100

        # Verify device 8 was NOT affected (still at initial state)
        d8_state = device_8.lights[0].get_state()
        assert d8_state["state"] == False
        assert d8_state["brightness"] == 0

    def test_multiple_devices_receive_own_messages(self):
        """Test that multiple devices each only respond to their own messages."""
        mock_bus = Mock()

        # Create devices 1, 5, and 10
        devices = {
            1: Bloc9Device(
                device_id=1,
                can_bus=mock_bus,
                switches_config={"s3": {"name": "Switch Device 1 S3"}},
            ),
            5: Bloc9Device(
                device_id=5,
                can_bus=mock_bus,
                switches_config={"s3": {"name": "Switch Device 5 S3"}},
            ),
            10: Bloc9Device(
                device_id=10,
                can_bus=mock_bus,
                switches_config={"s3": {"name": "Switch Device 10 S3"}},
            ),
        }

        # Create messages for each device (S3/S4 = 0x02180600)
        messages = {
            1: can.Message(
                arbitration_id=0x02180688,  # Device 1
                data=bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]),
                is_extended_id=True,
            ),
            5: can.Message(
                arbitration_id=0x021806A8,  # Device 5
                data=bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]),
                is_extended_id=True,
            ),
            10: can.Message(
                arbitration_id=0x021806D0,  # Device 10
                data=bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]),
                is_extended_id=True,
            ),
        }

        # Process device 10's message on all devices
        for device_id, device in devices.items():
            device.process_message(messages[10])

        # Only device 10 should be affected
        assert devices[1].switches[0].get_state() == False
        assert devices[5].switches[0].get_state() == False
        assert devices[10].switches[0].get_state() == True

        # Process device 5's message on all devices
        for device_id, device in devices.items():
            device.process_message(messages[5])

        # Now device 5 and 10 should be ON, device 1 still OFF
        assert devices[1].switches[0].get_state() == False
        assert devices[5].switches[0].get_state() == True
        assert devices[10].switches[0].get_state() == True

        # Process device 1's message on all devices
        for device_id, device in devices.items():
            device.process_message(messages[1])

        # Now all three should be ON, each from their own message
        assert devices[1].switches[0].get_state() == True
        assert devices[5].switches[0].get_state() == True
        assert devices[10].switches[0].get_state() == True

    def test_device_ignores_heartbeat_from_other_devices(self):
        """Test that devices ignore heartbeat messages from other devices."""
        mock_bus = Mock()

        device_7 = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Light Device 7 S5"}},
        )

        device_8 = Bloc9Device(
            device_id=8,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Light Device 8 S5"}},
        )

        # Create heartbeat message for device 8
        heartbeat_device_8 = can.Message(
            arbitration_id=0x000006C0,  # Device 8 heartbeat
            data=bytes([0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]),
            is_extended_id=True,
        )

        # Subscribe observers to both devices
        d7_observer = Mock()
        d8_observer = Mock()
        device_7.subscribe(d7_observer)
        device_8.subscribe(d8_observer)

        # Process device 8's heartbeat on both devices
        device_7.process_message(heartbeat_device_8)
        device_8.process_message(heartbeat_device_8)

        # Device 7 should NOT have called its observer (heartbeat not for it)
        assert d7_observer.call_count == 0

        # Device 8 SHOULD have called its observer (heartbeat is for it)
        assert d8_observer.call_count == 1

    def test_command_echo_only_processed_by_sender(self):
        """Test that command echo messages are only processed by the sender device."""
        mock_bus = Mock()

        device_5 = Bloc9Device(
            device_id=5,
            can_bus=mock_bus,
            lights_config={"s1": {"name": "Light Device 5 S1"}},
        )

        device_10 = Bloc9Device(
            device_id=10,
            can_bus=mock_bus,
            lights_config={"s1": {"name": "Light Device 10 S1"}},
        )

        # Command echo for device 5
        command_echo_device_5 = can.Message(
            arbitration_id=0x023606A8,  # Device 5 command echo
            data=bytes([0x00, 0x01, 0x00, 0x00]),
            is_extended_id=True,
        )

        # Subscribe observers
        d5_observer = Mock()
        d10_observer = Mock()
        device_5.lights[0].subscribe(d5_observer)
        device_10.lights[0].subscribe(d10_observer)

        # Process command echo on both devices
        device_5.process_message(command_echo_device_5)
        device_10.process_message(command_echo_device_5)

        # Neither device should have notified observers (command echoes are ignored)
        assert d5_observer.call_count == 0
        assert d10_observer.call_count == 0

        # Neither device's state should have changed
        assert device_5.lights[0].get_state()["state"] == False
        assert device_10.lights[0].get_state()["state"] == False

    def test_real_world_scenario_from_can_names_csv(self):
        """
        Test using actual arbitration IDs from can_names.csv.

        This verifies the real-world device IDs and message patterns work correctly.
        """
        mock_bus = Mock()

        # Create devices as documented in can_names.csv
        device_x26_id7 = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={
                "s1": {"name": "X26 S1"},
                "s2": {"name": "X26 S2"},
            },
        )

        device_x27_id8 = Bloc9Device(
            device_id=8,
            can_bus=mock_bus,
            lights_config={
                "s1": {"name": "X27 S1"},
                "s2": {"name": "X27 S2"},
            },
        )

        device_x20_id10 = Bloc9Device(
            device_id=10,
            can_bus=mock_bus,
            lights_config={
                "s1": {"name": "X20 S1"},
                "s2": {"name": "X20 S2"},
            },
        )

        # Message patterns from can_names.csv
        # 021606B8 = X26 ID:7 S1,S2
        # 021606C0 = X27 ID:8 S1,S2
        # 021606D0 = X20 ID:10 S1,S2

        # Turn ON S1 on device 7 (X26)
        msg_x26_s1_on = can.Message(
            arbitration_id=0x021606B8,
            data=bytes(
                [0x50, 0x00, 0x11, 0x01, 0x00, 0x00, 0x00, 0x00]
            ),  # S1 brightness=80, ON
            is_extended_id=True,
        )

        # Turn ON S1 on device 8 (X27)
        msg_x27_s1_on = can.Message(
            arbitration_id=0x021606C0,
            data=bytes(
                [0xC8, 0x00, 0x11, 0x01, 0x00, 0x00, 0x00, 0x00]
            ),  # S1 brightness=200, ON
            is_extended_id=True,
        )

        # Process X26's message on all devices
        device_x26_id7.process_message(msg_x26_s1_on)
        device_x27_id8.process_message(msg_x26_s1_on)
        device_x20_id10.process_message(msg_x26_s1_on)

        # Only X26 (device 7) should be affected
        assert device_x26_id7.lights[0].get_state()["state"] == True
        assert device_x26_id7.lights[0].get_state()["brightness"] == 80
        assert device_x27_id8.lights[0].get_state()["state"] == False
        assert device_x20_id10.lights[0].get_state()["state"] == False

        # Process X27's message on all devices
        device_x26_id7.process_message(msg_x27_s1_on)
        device_x27_id8.process_message(msg_x27_s1_on)
        device_x20_id10.process_message(msg_x27_s1_on)

        # Now X26 and X27 should be affected
        assert device_x26_id7.lights[0].get_state()["brightness"] == 80  # unchanged
        assert device_x27_id8.lights[0].get_state()["state"] == True
        assert device_x27_id8.lights[0].get_state()["brightness"] == 200
        assert device_x20_id10.lights[0].get_state()["state"] == False

    def test_matcher_registration_isolation(self):
        """
        Test that matchers are correctly registered per-device.

        Verifies that each device's _matcher_to_outputs mapping only contains
        entries for that device's arbitration IDs.
        """
        mock_bus = Mock()

        device_3 = Bloc9Device(
            device_id=3,
            can_bus=mock_bus,
            lights_config={
                "s1": {"name": "Device 3 S1"},
                "s3": {"name": "Device 3 S3"},
                "s5": {"name": "Device 3 S5"},
            },
        )

        device_9 = Bloc9Device(
            device_id=9,
            can_bus=mock_bus,
            lights_config={
                "s1": {"name": "Device 9 S1"},
                "s3": {"name": "Device 9 S3"},
                "s5": {"name": "Device 9 S5"},
            },
        )

        # Check device 3's matcher mapping
        device_3_patterns = set(device_3._matcher_to_outputs.keys())
        expected_device_3 = {
            0x02160698,  # S1/S2 for device 3
            0x02180698,  # S3/S4 for device 3
            0x021A0698,  # S5/S6 for device 3
        }
        assert device_3_patterns == expected_device_3

        # Check device 9's matcher mapping
        device_9_patterns = set(device_9._matcher_to_outputs.keys())
        expected_device_9 = {
            0x021606C8,  # S1/S2 for device 9
            0x021806C8,  # S3/S4 for device 9
            0x021A06C8,  # S5/S6 for device 9
        }
        assert device_9_patterns == expected_device_9

        # Verify no overlap
        assert device_3_patterns.isdisjoint(device_9_patterns)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
