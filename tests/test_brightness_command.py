#!/usr/bin/env python3
"""
Test case for sending brightness commands to Bloc9 devices over CAN bus.

This test verifies the brightness control command construction and transmission.
Tests use 0-255 brightness scale (not percentage).
Run with: cd scheiber/src && python ../../tests/test_brightness_command.py
"""

import sys
import os

# Add parent directory to path to import scheiber module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scheiber", "src"))

import unittest
from unittest.mock import Mock, patch, call
import can
from scheiber import bloc9_switch


class TestBrightnessCommand(unittest.TestCase):
    """Test brightness command generation and CAN bus transmission."""

    @patch("scheiber.can.interface.Bus")
    def test_brightness_0_percent_turns_off(self, mock_bus_class):
        """Test that brightness=0 sends OFF command (00 byte)."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus

        bloc9_switch("can1", bloc9_id=10, switch_nr=3, state=True, brightness=0)

        # Verify CAN ID construction: 0x02360600 | ((10 << 3) | 0x80)
        # 10 << 3 = 80 (0x50), | 0x80 = 0xD0
        expected_can_id = 0x023606D0
        expected_data = bytes([3, 0x00, 0x00, 0x00])  # Switch 3, OFF

        mock_bus.send.assert_called_once()
        sent_msg = mock_bus.send.call_args[0][0]
        self.assertEqual(sent_msg.arbitration_id, expected_can_id)
        self.assertEqual(sent_msg.data, expected_data)

    @patch("scheiber.can.interface.Bus")
    def test_brightness_128_mid_level(self, mock_bus_class):
        """Test that brightness=128 sends correct brightness byte."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus

        bloc9_switch("can1", bloc9_id=10, switch_nr=3, state=True, brightness=128)

        # Brightness 128 = mid-level brightness
        expected_can_id = 0x023606D0
        expected_data = bytes([3, 0x11, 0x00, 128])  # Switch 3, brightness mode, 128

        mock_bus.send.assert_called_once()
        sent_msg = mock_bus.send.call_args[0][0]
        self.assertEqual(sent_msg.arbitration_id, expected_can_id)
        self.assertEqual(sent_msg.data, expected_data)

    @patch("scheiber.can.interface.Bus")
    def test_brightness_255_turns_on(self, mock_bus_class):
        """Test that brightness=255 sends ON command (01 byte)."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus

        bloc9_switch("can1", bloc9_id=10, switch_nr=3, state=True, brightness=255)

        # Brightness 255 = turn on (without brightness control)
        expected_can_id = 0x023606D0
        expected_data = bytes([3, 0x01, 0x00, 0x00])  # Switch 3, ON

        mock_bus.send.assert_called_once()
        sent_msg = mock_bus.send.call_args[0][0]
        self.assertEqual(sent_msg.arbitration_id, expected_can_id)
        self.assertEqual(sent_msg.data, expected_data)

    @patch("scheiber.can.interface.Bus")
    def test_brightness_1_minimum(self, mock_bus_class):
        """Test that brightness=1 sends minimum non-zero brightness."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus

        bloc9_switch("can1", bloc9_id=10, switch_nr=3, state=True, brightness=1)

        # Brightness 1 = minimum non-zero
        expected_can_id = 0x023606D0

        mock_bus.send.assert_called_once()
        sent_msg = mock_bus.send.call_args[0][0]
        self.assertEqual(sent_msg.arbitration_id, expected_can_id)
        self.assertEqual(sent_msg.data[0], 3)  # switch_nr
        self.assertEqual(sent_msg.data[1], 0x11)  # brightness mode
        self.assertEqual(sent_msg.data[2], 0x00)
        self.assertEqual(sent_msg.data[3], 1)  # brightness byte

    @patch("scheiber.can.interface.Bus")
    def test_different_bloc9_ids(self, mock_bus_class):
        """Test brightness command with different Bloc9 IDs."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus

        # Test bloc9_id=3 with brightness=200
        bloc9_switch("can1", bloc9_id=3, switch_nr=0, state=True, brightness=200)

        # CAN ID: 3 << 3 = 24 (0x18), | 0x80 = 0x98
        expected_can_id = 0x02360698

        mock_bus.send.assert_called_once()
        sent_msg = mock_bus.send.call_args[0][0]
        self.assertEqual(sent_msg.arbitration_id, expected_can_id)
        self.assertEqual(sent_msg.data[0], 0)  # switch_nr
        self.assertEqual(sent_msg.data[1], 0x11)  # brightness mode
        self.assertEqual(sent_msg.data[2], 0x00)
        self.assertEqual(sent_msg.data[3], 200)  # brightness byte

    @patch("scheiber.can.interface.Bus")
    def test_different_switch_numbers(self, mock_bus_class):
        """Test brightness command with different switch numbers (S1-S6)."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus

        # Test all switches S1-S6 (switch_nr 0-5)
        for switch_nr in range(6):
            mock_bus.reset_mock()

            bloc9_switch(
                "can1", bloc9_id=10, switch_nr=switch_nr, state=True, brightness=128
            )

            expected_data = bytes([switch_nr, 0x11, 0x00, 128])

            mock_bus.send.assert_called_once()
            sent_msg = mock_bus.send.call_args[0][0]
            self.assertEqual(
                sent_msg.data[0], switch_nr, f"Failed for switch S{switch_nr+1}"
            )

    @patch("scheiber.can.interface.Bus")
    def test_bus_shutdown_called(self, mock_bus_class):
        """Test that bus.shutdown() is called even on success."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus

        bloc9_switch("can1", bloc9_id=10, switch_nr=3, state=True, brightness=128)

        # Verify shutdown was called
        mock_bus.shutdown.assert_called_once()

    @patch("scheiber.can.interface.Bus")
    def test_bus_shutdown_called_on_error(self, mock_bus_class):
        """Test that bus.shutdown() is called even when send fails."""
        mock_bus = Mock()
        mock_bus.send.side_effect = Exception("CAN send failed")
        mock_bus_class.return_value = mock_bus

        with self.assertRaises(Exception):
            bloc9_switch("can1", bloc9_id=10, switch_nr=3, state=True, brightness=128)

        # Verify shutdown was still called
        mock_bus.shutdown.assert_called_once()

    @patch("scheiber.can.interface.Bus")
    def test_brightness_range_values(self, mock_bus_class):
        """Test various brightness levels (0-255 scale)."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus

        test_cases = [
            # (brightness_level, expected_byte, expected_mode)
            (0, 0x00, 0x00),  # OFF
            (1, 0x11, 1),  # Min brightness
            (50, 0x11, 50),  # Low brightness
            (128, 0x11, 128),  # Mid brightness
            (200, 0x11, 200),  # High brightness
            (254, 0x11, 254),  # Max brightness with control
            (255, 0x01, 0x00),  # ON (without brightness control)
        ]

        for brightness, expected_mode, expected_brightness in test_cases:
            mock_bus.reset_mock()

            bloc9_switch(
                "can1", bloc9_id=10, switch_nr=3, state=True, brightness=brightness
            )

            sent_msg = mock_bus.send.call_args[0][0]
            self.assertEqual(
                sent_msg.data[0], 3, f"Switch number wrong for brightness={brightness}"
            )
            self.assertEqual(
                sent_msg.data[1],
                expected_mode,
                f"Mode byte wrong for brightness={brightness}",
            )
            self.assertEqual(
                sent_msg.data[2],
                0x00,
                f"Byte 2 should be 0 for brightness={brightness}",
            )

            if brightness == 255:
                # Special case: brightness=255 sends ON command
                self.assertEqual(
                    sent_msg.data[3],
                    0x00,
                    f"Brightness=255 should send ON (0x01 0x00 0x00)",
                )
            elif brightness == 0:
                # Special case: brightness=0 sends OFF command
                self.assertEqual(
                    sent_msg.data[3],
                    0x00,
                    f"Brightness=0 should send OFF (0x00 0x00 0x00)",
                )
            else:
                # Normal brightness mode
                self.assertEqual(
                    sent_msg.data[3],
                    expected_brightness,
                    f"Brightness {brightness} should send byte {expected_brightness}, got {sent_msg.data[3]}",
                )


class TestBrightnessCommandManual(unittest.TestCase):
    """Manual test that sends actual CAN messages (requires hardware)."""

    @unittest.skip("Requires actual CAN hardware - run manually with 'can1' interface")
    def test_brightness_sweep_manual(self):
        """
        Manual test: sweeps brightness from 0 to 255 on Bloc9 ID 10, Switch 3.

        To run manually:
        1. Ensure CAN interface 'can1' is available
        2. Uncomment the @unittest.skip decorator
        3. Run: cd scheiber/tools && python ../../tests/test_brightness_command.py
        """
        import time

        print("\n=== Manual Brightness Sweep Test ===")
        print("Bloc9 ID: 10, Switch: 3 (S4)")
        print("Sweeping brightness from 0 to 255 in steps of 25...\n")

        for brightness in range(0, 256, 25):
            print(f"Setting brightness to {brightness}...")
            bloc9_switch(
                "can1", bloc9_id=10, switch_nr=3, state=True, brightness=brightness
            )
            time.sleep(0.5)

        print("\nSweep complete!")


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
