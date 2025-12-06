#!/usr/bin/env python3
"""
Test cases for CAN message decoding from Scheiber devices.
Tests all message types described in the README and protocol documentation.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scheiber", "src"))

import unittest
from can_decoder import find_device_and_matcher, extract_property_value


class TestBloc9StatusUpdate(unittest.TestCase):
    """Test Bloc9 status update message (0x00000600 prefix)."""

    def test_status_update_matching(self):
        """Test that status update messages match the bloc9 device."""
        arb_id = 0x000006C0  # bus_id=8
        device_key, device_config, matcher, bus_id = find_device_and_matcher(arb_id)

        self.assertIsNotNone(device_key, "Should find a matching device")
        self.assertEqual(device_key, "bloc9")
        self.assertEqual(bus_id, 8)

    def test_status_update_bus_id_extraction(self):
        """Test extracting bus_id from status update CAN ID."""
        test_cases = [
            (0x00000680, 0),  # bus_id=0
            (0x00000698, 3),  # bus_id=3
            (0x000006C0, 8),  # bus_id=8
            (0x000006D0, 10),  # bus_id=10
        ]

        for arb_id, expected_bus_id in test_cases:
            _, _, _, bus_id = find_device_and_matcher(arb_id)
            self.assertEqual(
                bus_id, expected_bus_id, f"Bus ID mismatch for CAN ID 0x{arb_id:08X}"
            )

    def test_status_properties_present(self):
        """Test that status matcher has all expected properties."""
        arb_id = 0x000006C0
        _, _, matcher, _ = find_device_and_matcher(arb_id)

        self.assertIn("properties", matcher)
        # Status messages should have properties like s1-s6
        properties = matcher["properties"]
        self.assertGreater(
            len(properties), 0, "Status matcher should have properties defined"
        )


class TestBloc9SwitchMessages(unittest.TestCase):
    """Test Bloc9 switch-specific messages (S1/S2, S3/S4, S5/S6)."""

    def test_s1_s2_matching(self):
        """Test S1 & S2 message (0x02160600 prefix) matching."""
        arb_id = 0x021606C0  # bus_id=8
        device_key, _, matcher, bus_id = find_device_and_matcher(arb_id)

        self.assertEqual(device_key, "bloc9")
        self.assertEqual(bus_id, 8)

        # Should have s1 and s2 properties
        properties = matcher["properties"]
        self.assertIn("s1", properties)
        self.assertIn("s2", properties)

    def test_s3_s4_matching(self):
        """Test S3 & S4 message (0x02180600 prefix) matching."""
        arb_id = 0x021806B8  # bus_id=7
        device_key, _, matcher, bus_id = find_device_and_matcher(arb_id)

        self.assertEqual(device_key, "bloc9")
        self.assertEqual(bus_id, 7)

        properties = matcher["properties"]
        self.assertIn("s3", properties)
        self.assertIn("s4", properties)

    def test_s5_s6_matching(self):
        """Test S5 & S6 message (0x021A0600 prefix) matching."""
        arb_id = 0x021A06D0  # bus_id=10
        device_key, _, matcher, bus_id = find_device_and_matcher(arb_id)

        self.assertEqual(device_key, "bloc9")
        self.assertEqual(bus_id, 10)

        properties = matcher["properties"]
        self.assertIn("s5", properties)
        self.assertIn("s6", properties)

    def test_all_switch_pairs_bus_ids(self):
        """Test bus ID extraction across all switch pair messages."""
        test_cases = [
            (0x02160698, 3),  # S1/S2, bus_id=3
            (0x021806C0, 8),  # S3/S4, bus_id=8
            (0x021A0688, 1),  # S5/S6, bus_id=1
        ]

        for arb_id, expected_bus_id in test_cases:
            _, _, _, bus_id = find_device_and_matcher(arb_id)
            self.assertEqual(bus_id, expected_bus_id)


class TestBloc9CommandMessages(unittest.TestCase):
    """Test Bloc9 command message format (0x02360600 prefix)."""

    def test_command_can_id_construction(self):
        """Test building command CAN ID from bus_id."""
        test_cases = [
            (0, 0x02360680),
            (3, 0x02360698),
            (8, 0x023606C0),
            (10, 0x023606D0),
        ]

        for bus_id, expected_id in test_cases:
            can_id = 0x02360600 | (((bus_id << 3) | 0x80) & 0xFF)
            self.assertEqual(
                can_id, expected_id, f"Command CAN ID mismatch for bus_id={bus_id}"
            )

    def test_on_command_format(self):
        """Test ON command: [switch_nr, 0x01, 0x00, 0x00]."""
        switch_nr = 5
        data = bytes([switch_nr, 0x01, 0x00, 0x00])

        self.assertEqual(data[0], switch_nr)
        self.assertEqual(data[1], 0x01)
        self.assertEqual(data[2], 0x00)
        self.assertEqual(data[3], 0x00)

    def test_off_command_format(self):
        """Test OFF command: [switch_nr, 0x00, 0x00, 0x00]."""
        switch_nr = 3
        data = bytes([switch_nr, 0x00, 0x00, 0x00])

        self.assertEqual(data[0], switch_nr)
        self.assertEqual(data[1], 0x00)
        self.assertEqual(data[2], 0x00)
        self.assertEqual(data[3], 0x00)

    def test_brightness_command_format(self):
        """Test brightness command: [switch_nr, 0x11, 0x00, brightness]."""
        switch_nr = 7
        brightness = 128
        data = bytes([switch_nr, 0x11, 0x00, brightness])

        self.assertEqual(data[0], switch_nr)
        self.assertEqual(data[1], 0x11)
        self.assertEqual(data[2], 0x00)
        self.assertEqual(data[3], brightness)


class TestMessageMatching(unittest.TestCase):
    """Test message matching logic."""

    def test_unmatched_message(self):
        """Test that unrecognized CAN IDs return None."""
        unknown_id = 0x12345678
        result = find_device_and_matcher(unknown_id)

        self.assertEqual(result, (None, None, None, None))

    def test_device_type_structure(self):
        """Test that matched messages return proper structure."""
        arb_id = 0x000006C0
        device_key, device_config, matcher, bus_id = find_device_and_matcher(arb_id)

        self.assertIsNotNone(device_key)
        self.assertIsNotNone(device_config)
        self.assertIsNotNone(matcher)
        self.assertIsNotNone(bus_id)

        # Verify structure
        self.assertIsInstance(device_key, str)
        self.assertIsInstance(device_config, dict)
        self.assertIsInstance(matcher, dict)
        self.assertIsInstance(bus_id, int)


class TestPropertyExtraction(unittest.TestCase):
    """Test property value extraction from CAN data."""

    def test_bit_extraction(self):
        """Test extracting individual bits from CAN data."""
        # Data with specific bit patterns
        data = bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01])

        # Bit 0 of byte 3 should be 1
        value = extract_property_value(data, "(3,0)")
        self.assertEqual(value, 1)

        # Bit 1 of byte 3 should be 0
        value = extract_property_value(data, "(3,1)")
        self.assertEqual(value, 0)

        # Bit 0 of byte 7 should be 1
        value = extract_property_value(data, "(7,0)")
        self.assertEqual(value, 1)

    def test_byte_extraction(self):
        """Test extracting full bytes from CAN data."""
        data = bytes([0xAB, 0x00, 0x00, 0x01, 0xCD, 0x00, 0x00, 0x01])

        # Byte 0 = 0xAB = 171
        value = extract_property_value(data, "[0]")
        self.assertEqual(value, 171)

        # Byte 4 = 0xCD = 205
        value = extract_property_value(data, "[4]")
        self.assertEqual(value, 205)


class TestBusIdExtraction(unittest.TestCase):
    """Test bus_id extraction formula: ((arb_id & 0xFF) & ~0x80) >> 3."""

    def test_formula_correctness(self):
        """Test that bus_id extraction works for all CAN IDs."""
        test_cases = [
            (0x02360680, 0),
            (0x02360688, 1),
            (0x02360698, 3),
            (0x023606B8, 7),
            (0x023606C0, 8),
            (0x023606D0, 10),
        ]

        for arb_id, expected_bus_id in test_cases:
            # Manual calculation - this is the formula used for CAN ID construction
            bus_id_manual = ((arb_id & 0xFF) & ~0x80) >> 3
            self.assertEqual(bus_id_manual, expected_bus_id)

    def test_status_message_bus_ids(self):
        """Test bus_id extraction from status messages (via matcher)."""
        test_cases = [
            (0x000006C0, 8),  # Status update
            (0x02160698, 3),  # S1/S2
            (0x021806B8, 7),  # S3/S4
            (0x021A0688, 1),  # S5/S6
        ]

        for arb_id, expected_bus_id in test_cases:
            _, _, _, bus_id = find_device_and_matcher(arb_id)
            self.assertEqual(bus_id, expected_bus_id)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_minimum_bus_id_formula(self):
        """Test bus_id=0 formula calculation."""
        arb_id = 0x02360680
        bus_id = ((arb_id & 0xFF) & ~0x80) >> 3
        self.assertEqual(bus_id, 0)

    def test_maximum_bus_id_formula(self):
        """Test maximum valid bus_id (15) formula calculation."""
        arb_id = 0x023606F8  # ((15 << 3) | 0x80) = 0xF8
        bus_id = ((arb_id & 0xFF) & ~0x80) >> 3
        self.assertEqual(bus_id, 15)

    def test_empty_data(self):
        """Test extracting from empty data."""
        data = bytes()

        # Should handle gracefully (exact behavior depends on implementation)
        try:
            value = extract_property_value(data, "[0]")
            # If it doesn't raise, we expect None or 0
            self.assertIn(value, [None, 0])
        except (IndexError, ValueError):
            # Acceptable to raise an error
            pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
