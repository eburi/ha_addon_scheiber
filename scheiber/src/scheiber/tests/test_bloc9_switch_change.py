"""
Test Bloc9 switch change message processing.

Verifies correct parsing of 8-byte switch state change messages according
to the format documented in device_types.yaml:
- Bytes 0-3: Lower switch (S1/S3/S5) - brightness at byte 0, state bit at byte 3
- Bytes 4-7: Higher switch (S2/S4/S6) - brightness at byte 4, state bit at byte 7
"""

from unittest.mock import Mock
import pytest
import can
from scheiber.bloc9 import Bloc9Device


class TestBloc9SwitchChange:
    """Test switch state change message processing."""

    def test_s5_s6_message_format_brightness_and_state(self):
        """Test S5/S6 message with brightness in byte 0 and state in byte 3."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={
                "s5": {"name": "Light S5", "entity_id": "light_s5"},
                "s6": {"name": "Light S6", "entity_id": "light_s6"},
            },
        )

        light_s5 = device.lights[0]
        light_s6 = device.lights[1]

        # Message: S5 brightness=107 ON, S6 brightness=0 OFF
        # Data: [s5_brightness, 0, 0, s5_state_bit, s6_brightness, 0, 0, s6_state_bit]
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([0x6B, 0x00, 0x11, 0x01, 0x00, 0x00, 0x01, 0x00]),
            is_extended_id=True,
        )

        device.process_message(msg, "s5_s6_change")

        # Verify S5 state
        s5_state = light_s5.get_state()
        assert s5_state["state"] == True
        assert s5_state["brightness"] == 107

        # Verify S6 state
        s6_state = light_s6.get_state()
        assert s6_state["state"] == False
        assert s6_state["brightness"] == 0

    def test_s5_s6_both_on_different_brightness(self):
        """Test S5 and S6 both ON with different brightness levels."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={
                "s5": {"name": "Light S5", "entity_id": "light_s5"},
                "s6": {"name": "Light S6", "entity_id": "light_s6"},
            },
        )

        light_s5 = device.lights[0]
        light_s6 = device.lights[1]

        # S5 brightness=200 ON, S6 brightness=50 ON
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([200, 0x00, 0x00, 0x01, 50, 0x00, 0x00, 0x01]),
            is_extended_id=True,
        )

        device.process_message(msg, "s5_s6_change")

        assert light_s5.get_state() == {"state": True, "brightness": 200}
        assert light_s6.get_state() == {"state": True, "brightness": 50}

    def test_s5_s6_both_off(self):
        """Test S5 and S6 both OFF."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={
                "s5": {"name": "Light S5", "entity_id": "light_s5"},
                "s6": {"name": "Light S6", "entity_id": "light_s6"},
            },
        )

        light_s5 = device.lights[0]
        light_s6 = device.lights[1]

        # Both OFF
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([0, 0, 0, 0, 0, 0, 0, 0]),
            is_extended_id=True,
        )

        device.process_message(msg, "s5_s6_change")

        assert light_s5.get_state() == {"state": False, "brightness": 0}
        assert light_s6.get_state() == {"state": False, "brightness": 0}

    def test_s1_s2_message_format(self):
        """Test S1/S2 message parsing."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=3,
            can_bus=mock_bus,
            lights_config={
                "s1": {"name": "Light S1", "entity_id": "light_s1"},
                "s2": {"name": "Light S2", "entity_id": "light_s2"},
            },
        )

        light_s1 = device.lights[0]
        light_s2 = device.lights[1]

        # S1 brightness=128 ON, S2 brightness=255 ON
        msg = can.Message(
            arbitration_id=0x02160698,  # S1/S2 for device 3
            data=bytes([128, 0x00, 0x00, 0x01, 255, 0x00, 0x00, 0x01]),
            is_extended_id=True,
        )

        device.process_message(msg, "s1_s2_change")

        assert light_s1.get_state() == {"state": True, "brightness": 128}
        assert light_s2.get_state() == {"state": True, "brightness": 255}

    def test_s3_s4_message_format(self):
        """Test S3/S4 message parsing."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=5,
            can_bus=mock_bus,
            lights_config={
                "s3": {"name": "Light S3", "entity_id": "light_s3"},
                "s4": {"name": "Light S4", "entity_id": "light_s4"},
            },
        )

        light_s3 = device.lights[0]
        light_s4 = device.lights[1]

        # S3 brightness=75 ON, S4 OFF
        msg = can.Message(
            arbitration_id=0x021806A8,  # S3/S4 for device 5
            data=bytes([75, 0x00, 0x00, 0x01, 0, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )

        device.process_message(msg, "s3_s4_change")

        assert light_s3.get_state() == {"state": True, "brightness": 75}
        assert light_s4.get_state() == {"state": False, "brightness": 0}

    def test_dimming_threshold_below(self):
        """Test brightness at/below dimming threshold (<=2) without state bit."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Light S5", "entity_id": "light_s5"}},
        )

        light_s5 = device.lights[0]

        # Brightness=2 WITHOUT state bit, but brightness >0 means ON
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([2, 0x00, 0x00, 0x00, 0, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )

        device.process_message(msg, "s5_s6_change")

        # Brightness 2 still results in ON (effective_brightness > 0)
        assert light_s5.get_state() == {"state": True, "brightness": 2}

    def test_dimming_threshold_above(self):
        """Test brightness above dimming threshold results in ON even without state bit."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Light S5", "entity_id": "light_s5"}},
        )

        light_s5 = device.lights[0]

        # Brightness=3 without state bit should still be ON due to threshold
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([3, 0x00, 0x00, 0x00, 0, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )

        device.process_message(msg, "s5_s6_change")

        assert light_s5.get_state() == {"state": True, "brightness": 3}

    def test_state_bit_overrides_brightness_zero(self):
        """Test Bloc9 quirk: state bit ON with brightness 0 becomes brightness 255."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Light S5", "entity_id": "light_s5"}},
        )

        light_s5 = device.lights[0]

        # Brightness=0 but state bit=1 triggers Bloc9 quirk: full brightness
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([0, 0x00, 0x00, 0x01, 0, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )

        device.process_message(msg, "s5_s6_change")

        # Bloc9 quirk: state=ON + brightness=0 → brightness=255
        assert light_s5.get_state() == {"state": True, "brightness": 255}

    def test_message_too_short_warning(self):
        """Test that messages shorter than 8 bytes log warning and don't crash."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Light S5", "entity_id": "light_s5"}},
        )

        light_s5 = device.lights[0]
        initial_state = light_s5.get_state()

        # Short message (only 4 bytes)
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([100, 0x00, 0x00, 0x01]),
            is_extended_id=True,
        )

        # Should not crash
        device.process_message(msg, "s5_s6_change")

        # State should be unchanged
        assert light_s5.get_state() == initial_state

    def test_switch_not_light_processing(self):
        """Test that switches (not lights) are also processed correctly."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            switches_config={
                "s5": {"name": "Switch S5", "entity_id": "switch_s5"},
                "s6": {"name": "Switch S6", "entity_id": "switch_s6"},
            },
        )

        switch_s5 = device.switches[0]
        switch_s6 = device.switches[1]

        # S5 ON, S6 OFF
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([100, 0x00, 0x00, 0x01, 0, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )

        device.process_message(msg, "s5_s6_change")

        assert switch_s5.get_state() == True
        assert switch_s6.get_state() == False

    def test_mixed_light_and_switch(self):
        """Test processing when one output is a light and the other is a switch."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Light S5", "entity_id": "light_s5"}},
            switches_config={"s6": {"name": "Switch S6", "entity_id": "switch_s6"}},
        )

        light_s5 = device.lights[0]
        switch_s6 = device.switches[0]

        # S5 brightness=150 ON, S6 ON
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([150, 0x00, 0x00, 0x01, 0, 0x00, 0x00, 0x01]),
            is_extended_id=True,
        )

        device.process_message(msg, "s5_s6_change")

        assert light_s5.get_state() == {"state": True, "brightness": 150}
        assert switch_s6.get_state() == True

    def test_only_lower_switch_configured(self):
        """Test when only the lower switch (S5) is configured."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Light S5", "entity_id": "light_s5"}},
        )

        light_s5 = device.lights[0]

        # S5 ON, S6 data present but not configured
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([100, 0x00, 0x00, 0x01, 200, 0x00, 0x00, 0x01]),
            is_extended_id=True,
        )

        # Should not crash even though S6 is not configured
        device.process_message(msg, "s5_s6_change")

        assert light_s5.get_state() == {"state": True, "brightness": 100}

    def test_only_higher_switch_configured(self):
        """Test when only the higher switch (S6) is configured."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s6": {"name": "Light S6", "entity_id": "light_s6"}},
        )

        light_s6 = device.lights[0]

        # S5 data present but not configured, S6 ON
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([100, 0x00, 0x00, 0x01, 200, 0x00, 0x00, 0x01]),
            is_extended_id=True,
        )

        # Should not crash even though S5 is not configured
        device.process_message(msg, "s5_s6_change")

        assert light_s6.get_state() == {"state": True, "brightness": 200}

    def test_observer_notification_on_state_change(self):
        """Test that observers are notified when state changes."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Light S5", "entity_id": "light_s5"}},
        )

        light_s5 = device.lights[0]
        observer = Mock()
        light_s5.subscribe(observer)

        # Send state change message
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([100, 0x00, 0x00, 0x01, 0, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )

        device.process_message(msg, "s5_s6_change")

        # Observer should be called
        observer.assert_called_once()
        call_arg = observer.call_args[0][0]
        assert call_arg["state"] == True
        assert call_arg["brightness"] == 100

    def test_no_observer_notification_when_state_unchanged(self):
        """Test that observers are NOT notified when state doesn't change."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={"s5": {"name": "Light S5", "entity_id": "light_s5"}},
        )

        light_s5 = device.lights[0]

        # Set initial state
        msg1 = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([100, 0x00, 0x00, 0x01, 0, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )
        device.process_message(msg1, "s5_s6_change")

        # Subscribe observer after initial state is set
        observer = Mock()
        light_s5.subscribe(observer)

        # Send same state again
        msg2 = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([100, 0x00, 0x00, 0x01, 0, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )
        device.process_message(msg2, "s5_s6_change")

        # Observer should NOT be called
        observer.assert_not_called()

    def test_actual_log_message_from_bug_report(self):
        """Test parsing the actual message from the bug report that was failing."""
        mock_bus = Mock()
        device = Bloc9Device(
            device_id=7,
            can_bus=mock_bus,
            lights_config={
                "s5": {"name": "Main Light Cockpit", "entity_id": "main_light_cockpit"}
            },
        )

        light = device.lights[0]

        # Actual message from log: Data=6b00110100000101
        # Should parse as: S5 brightness=0x6b (107) ON, S6 brightness=0x00 OFF
        msg = can.Message(
            arbitration_id=0x021A06B8,
            data=bytes([0x6B, 0x00, 0x11, 0x01, 0x00, 0x00, 0x01, 0x01]),
            is_extended_id=True,
        )

        device.process_message(msg, "s5_s6_change")

        # Should correctly parse S5 as ON with brightness 107
        assert light.get_state() == {"state": True, "brightness": 107}
