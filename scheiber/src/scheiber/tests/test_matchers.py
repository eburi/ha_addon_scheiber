"""Tests for Matcher class."""

import pytest
import can
from scheiber.matchers import Matcher


def make_message(arbitration_id):
    """Helper to create a CAN message with given ID."""
    return can.Message(arbitration_id=arbitration_id, data=[0] * 8)


class TestMatcher:
    """Test Matcher pattern/mask matching."""

    def test_exact_match(self):
        """Test exact match without mask."""
        matcher = Matcher(pattern=0x12345678, mask=0xFFFFFFFF)
        assert matcher.matches(make_message(0x12345678))
        assert not matcher.matches(make_message(0x12345679))

    def test_masked_match(self):
        """Test matching with mask to ignore lower bits."""
        # Match upper 24 bits, ignore lower 8 bits
        matcher = Matcher(pattern=0x12345600, mask=0xFFFFFF00)
        assert matcher.matches(make_message(0x12345600))
        assert matcher.matches(make_message(0x12345601))
        assert matcher.matches(make_message(0x123456FF))
        assert not matcher.matches(make_message(0x12345700))

    def test_bloc9_status_matcher(self):
        """Test Bloc9 status message matching."""
        matcher = Matcher(pattern=0x00000600, mask=0xFFFFFF00)

        # Should match messages with device IDs in lower byte
        assert matcher.matches(make_message(0x00000600))  # Device 0
        assert matcher.matches(make_message(0x00000650))  # Device 10 (0x50 = (10<<3)|0)
        assert matcher.matches(make_message(0x000006D0))  # Device 10 with MSB set

        # Should not match different message types
        assert not matcher.matches(make_message(0x00000700))
        assert not matcher.matches(make_message(0x02160600))

    def test_bloc9_command_matcher(self):
        """Test Bloc9 command message matching."""
        device_id = 10
        command_id = 0x02360600 | ((device_id << 3) | 0x80)

        matcher = Matcher(pattern=command_id, mask=0xFFFFFFFF)
        assert matcher.matches(make_message(command_id))
        assert not matcher.matches(make_message(command_id + 1))

    def test_string_representation(self):
        """Test human-readable string representation."""
        matcher = Matcher(pattern=0x12345678, mask=0xFFFFFF00)
        str_repr = str(matcher)

        assert "0x12345678" in str_repr or "0x12345678" in str_repr.upper()
        assert "0xffffff00" in str_repr or "0xFFFFFF00" in str_repr
