"""
Test Bloc9 CAN command generation.

Verifies that the correct CAN messages are sent for switch commands.
"""

from unittest.mock import Mock, call

import pytest

from scheiber.bloc9 import Bloc9Device


class TestBloc9Commands:
    """Test Bloc9 CAN command generation."""

    def test_bloc9_7_s5_off_command(self):
        """Test that Bloc9 device 7 S5 OFF sends correct CAN message."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(device_id=7, can_bus=mock_bus)

        # Execute: Turn OFF S5 (switch_nr=4)
        device._send_switch_command(switch_nr=4, state=False, brightness=0)

        # Verify: CAN message sent with correct arbitration ID and data
        expected_arbitration_id = 0x023606B8  # (7 << 3) | 0x80 = 0xB8
        expected_data = bytes([0x04, 0x00, 0x00, 0x00])  # S5 OFF

        mock_bus.send_message.assert_called_once_with(
            expected_arbitration_id, expected_data
        )

    def test_bloc9_7_s5_on_command(self):
        """Test that Bloc9 device 7 S5 ON sends correct CAN message."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(device_id=7, can_bus=mock_bus)

        # Execute: Turn ON S5 with full brightness
        device._send_switch_command(switch_nr=4, state=True, brightness=255)

        # Verify: CAN message sent with correct arbitration ID and data
        expected_arbitration_id = 0x023606B8
        expected_data = bytes([0x04, 0x01, 0x00, 0x00])  # S5 ON (full brightness)

        mock_bus.send_message.assert_called_once_with(
            expected_arbitration_id, expected_data
        )

    def test_bloc9_7_s5_pwm_command(self):
        """Test that Bloc9 device 7 S5 with PWM brightness sends correct CAN message."""
        # Setup
        mock_bus = Mock()
        device = Bloc9Device(device_id=7, can_bus=mock_bus)

        # Execute: Set S5 to 128 brightness (PWM mode)
        device._send_switch_command(switch_nr=4, state=True, brightness=128)

        # Verify: CAN message sent with PWM mode
        expected_arbitration_id = 0x023606B8
        expected_data = bytes([0x04, 0x11, 0x00, 0x80])  # S5 PWM brightness=128

        mock_bus.send_message.assert_called_once_with(
            expected_arbitration_id, expected_data
        )

    def test_bloc9_arbitration_id_calculation(self):
        """Test arbitration ID calculation for different device IDs."""
        test_cases = [
            (1, 0x02360688),  # (1 << 3) | 0x80 = 0x88
            (7, 0x023606B8),  # (7 << 3) | 0x80 = 0xB8
            (10, 0x023606D0),  # (10 << 3) | 0x80 = 0xD0
        ]

        for device_id, expected_can_id in test_cases:
            mock_bus = Mock()
            device = Bloc9Device(device_id=device_id, can_bus=mock_bus)

            # Send any command
            device._send_switch_command(switch_nr=0, state=True, brightness=255)

            # Verify correct CAN ID
            actual_can_id = mock_bus.send_message.call_args[0][0]
            assert (
                actual_can_id == expected_can_id
            ), f"Device {device_id}: expected 0x{expected_can_id:08X}, got 0x{actual_can_id:08X}"

    def test_bloc9_all_switches(self):
        """Test that all switch numbers (S1-S6) generate correct data."""
        mock_bus = Mock()
        device = Bloc9Device(device_id=7, can_bus=mock_bus)

        # Test all 6 switches
        for switch_nr in range(6):
            mock_bus.reset_mock()
            device._send_switch_command(switch_nr=switch_nr, state=True, brightness=255)

            # Verify switch number is in first byte
            actual_data = mock_bus.send_message.call_args[0][1]
            assert (
                actual_data[0] == switch_nr
            ), f"S{switch_nr+1}: expected byte 0 = {switch_nr}, got {actual_data[0]}"

    def test_bloc9_dimming_threshold_low(self):
        """Test that brightness <= 2 sends OFF command."""
        mock_bus = Mock()
        device = Bloc9Device(device_id=7, can_bus=mock_bus)

        # Test brightness values at/below threshold
        for brightness in [0, 1, 2]:
            mock_bus.reset_mock()
            device._send_switch_command(switch_nr=4, state=True, brightness=brightness)

            # Verify OFF command (byte 1 = 0x00)
            actual_data = mock_bus.send_message.call_args[0][1]
            assert (
                actual_data[1] == 0x00
            ), f"Brightness {brightness}: should send OFF (0x00), got 0x{actual_data[1]:02X}"

    def test_bloc9_dimming_threshold_high(self):
        """Test that brightness >= 253 sends ON command (no PWM)."""
        mock_bus = Mock()
        device = Bloc9Device(device_id=7, can_bus=mock_bus)

        # Test brightness values at/above threshold
        for brightness in [253, 254, 255]:
            mock_bus.reset_mock()
            device._send_switch_command(switch_nr=4, state=True, brightness=brightness)

            # Verify ON command (byte 1 = 0x01)
            actual_data = mock_bus.send_message.call_args[0][1]
            assert (
                actual_data[1] == 0x01
            ), f"Brightness {brightness}: should send ON (0x01), got 0x{actual_data[1]:02X}"

    def test_bloc9_pwm_range(self):
        """Test that brightness 3-252 sends PWM command."""
        mock_bus = Mock()
        device = Bloc9Device(device_id=7, can_bus=mock_bus)

        # Test PWM range
        for brightness in [3, 50, 128, 200, 252]:
            mock_bus.reset_mock()
            device._send_switch_command(switch_nr=4, state=True, brightness=brightness)

            # Verify PWM command (byte 1 = 0x11, byte 3 = brightness)
            actual_data = mock_bus.send_message.call_args[0][1]
            assert (
                actual_data[1] == 0x11
            ), f"Brightness {brightness}: should send PWM (0x11), got 0x{actual_data[1]:02X}"
            assert (
                actual_data[3] == brightness
            ), f"Brightness {brightness}: byte 3 should be {brightness}, got {actual_data[3]}"

    def test_bloc9_7_s5_debug_arbitration_id(self):
        """Debug test to verify arbitration ID calculation step by step."""
        mock_bus = Mock()
        device = Bloc9Device(device_id=7, can_bus=mock_bus)

        # Manually calculate expected CAN ID
        device_id = 7
        low_byte = ((device_id << 3) | 0x80) & 0xFF
        expected_can_id = 0x02360600 | low_byte

        print(f"\nDebug info:")
        print(f"  device_id = {device_id}")
        print(f"  device_id << 3 = {device_id << 3} (0x{device_id << 3:02X})")
        print(
            f"  (device_id << 3) | 0x80 = {(device_id << 3) | 0x80} (0x{(device_id << 3) | 0x80:02X})"
        )
        print(f"  low_byte = {low_byte} (0x{low_byte:02X})")
        print(f"  expected_can_id = 0x{expected_can_id:08X}")
        print(f"  device.device_id = {device.device_id}")

        # Send command
        device._send_switch_command(switch_nr=4, state=False, brightness=0)

        # Get actual CAN ID
        actual_can_id = mock_bus.send_message.call_args[0][0]
        print(f"  actual_can_id = 0x{actual_can_id:08X}")

        assert (
            actual_can_id == expected_can_id
        ), f"Expected 0x{expected_can_id:08X}, got 0x{actual_can_id:08X}"

    def test_can_bus_extended_id_flag(self):
        """Test that ScheiberCanBus creates CAN messages with extended_id=True."""
        from unittest.mock import MagicMock, patch

        import can

        from scheiber.can_bus import ScheiberCanBus

        # Mock the actual CAN bus interface
        with patch("can.interface.Bus") as mock_bus_class:
            mock_bus_instance = MagicMock()
            mock_bus_class.return_value = mock_bus_instance

            # Create bus and initialize it by starting listening
            bus = ScheiberCanBus("can1")
            bus.start_listening(lambda msg: None)

            # Send a message with extended CAN ID
            arbitration_id = 0x023606B8
            data = bytes([0x04, 0x00, 0x00, 0x00])
            bus.send_message(arbitration_id, data)

            # Verify that bus.send() was called
            assert mock_bus_instance.send.called, "CAN bus send() was not called"

            # Get the can.Message object that was passed to send()
            sent_message = mock_bus_instance.send.call_args[0][0]

            # Verify it's a can.Message with correct properties
            assert isinstance(
                sent_message, can.Message
            ), f"Expected can.Message, got {type(sent_message)}"
            assert (
                sent_message.arbitration_id == arbitration_id
            ), f"Expected arbitration_id 0x{arbitration_id:08X}, got 0x{sent_message.arbitration_id:08X}"
            assert (
                sent_message.is_extended_id is True
            ), f"Expected is_extended_id=True, got {sent_message.is_extended_id}"
            assert (
                sent_message.data == data
            ), f"Expected data {data.hex()}, got {sent_message.data.hex()}"

            bus.stop()
