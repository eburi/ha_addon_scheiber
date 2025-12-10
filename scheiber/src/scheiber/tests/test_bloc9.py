"""
Tests for Bloc9Device CAN protocol implementation.

Critical tests for dimming threshold, CAN ID construction, command format,
and message processing based on v5 test suite (test_dimming_threshold.py, test_brightness_command.py).
"""

import pytest
from unittest.mock import Mock, call

from scheiber.bloc9 import Bloc9Device


class TestBloc9Initialization:
    """Test Bloc9Device initialization."""

    def test_initialization_minimal(self, mock_can_bus, mock_logger):
        """Test minimal initialization with only required parameters."""
        device = Bloc9Device(device_id=3, can_bus=mock_can_bus, logger=mock_logger)

        assert device.device_id == 3
        assert device.name == "Bloc9_3"
        assert len(device.lights) == 0
        assert len(device.switches) == 0

    def test_initialization_with_name(self, mock_can_bus, mock_logger):
        """Test initialization with custom name."""
        device = Bloc9Device(
            device_id=5, name="Salon Lights", can_bus=mock_can_bus, logger=mock_logger
        )

        assert device.device_id == 5
        assert device.name == "Salon Lights"

    def test_initialization_with_lights(self, mock_can_bus, mock_logger):
        """Test initialization with lights configuration."""
        lights_config = {
            "underwater": {"switch_nr": 0, "name": "Underwater Light"},
            "cockpit": {"switch_nr": 1, "name": "Cockpit Light"},
        }

        device = Bloc9Device(
            device_id=3,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        assert len(device.lights) == 2
        assert "underwater" in device.lights
        assert "cockpit" in device.lights
        assert device.lights["underwater"].switch_nr == 0
        assert device.lights["cockpit"].switch_nr == 1

    def test_initialization_with_switches(self, mock_can_bus, mock_logger):
        """Test initialization with switches configuration."""
        switches_config = {
            "pump1": {"switch_nr": 3, "name": "Bilge Pump 1"},
            "pump2": {"switch_nr": 4, "name": "Bilge Pump 2"},
        }

        device = Bloc9Device(
            device_id=7,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        assert len(device.switches) == 2
        assert "pump1" in device.switches
        assert "pump2" in device.switches
        assert device.switches["pump1"].switch_nr == 3
        assert device.switches["pump2"].switch_nr == 4

    def test_initialization_mixed_outputs(self, mock_can_bus, mock_logger):
        """Test initialization with both lights and switches."""
        lights_config = {"nav_light": {"switch_nr": 0, "name": "Navigation Light"}}
        switches_config = {"horn": {"switch_nr": 1, "name": "Horn"}}

        device = Bloc9Device(
            device_id=10,
            lights_config=lights_config,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        assert len(device.lights) == 1
        assert len(device.switches) == 1
        assert "nav_light" in device.lights
        assert "horn" in device.switches


class TestBloc9CanIdConstruction:
    """Test CAN arbitration ID construction following v5 protocol."""

    def test_can_id_construction_device_3(self, mock_can_bus, mock_logger):
        """Test CAN ID for device_id=3: 0x023606D8."""
        device = Bloc9Device(device_id=3, can_bus=mock_can_bus, logger=mock_logger)

        switches_config = {"test": {"switch_nr": 0, "name": "Test"}}
        device = Bloc9Device(
            device_id=3,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        # Trigger a switch command
        device.switches["test"].turn_on()

        # Check CAN ID construction: 0x02360600 | ((3 << 3) | 0x80) = 0x02360600 | 0x98 = 0x02360698
        expected_id = 0x02360600 | ((3 << 3) | 0x80)
        assert expected_id == 0x02360698

        # Verify the sent message
        mock_can_bus.send.assert_called_once()
        sent_msg = mock_can_bus.send.call_args[0][0]
        assert sent_msg.arbitration_id == 0x02360698

    def test_can_id_construction_device_10(self, mock_can_bus, mock_logger):
        """Test CAN ID for device_id=10: 0x023606D0."""
        switches_config = {"test": {"switch_nr": 0, "name": "Test"}}
        device = Bloc9Device(
            device_id=10,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.switches["test"].turn_on()

        # CAN ID: 0x02360600 | ((10 << 3) | 0x80) = 0x02360600 | 0xD0 = 0x023606D0
        expected_id = 0x02360600 | ((10 << 3) | 0x80)
        assert expected_id == 0x023606D0

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert sent_msg.arbitration_id == 0x023606D0

    def test_can_id_construction_device_15(self, mock_can_bus, mock_logger):
        """Test CAN ID for device_id=15 (max value)."""
        switches_config = {"test": {"switch_nr": 0, "name": "Test"}}
        device = Bloc9Device(
            device_id=15,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.switches["test"].turn_on()

        # CAN ID: 0x02360600 | ((15 << 3) | 0x80) = 0x02360600 | 0xF8 = 0x023606F8
        expected_id = 0x02360600 | ((15 << 3) | 0x80)
        assert expected_id == 0x023606F8

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert sent_msg.arbitration_id == 0x023606F8


class TestBloc9DimmingThreshold:
    """
    Test dimming threshold behavior (CRITICAL - must match v5).

    Protocol rules:
    - brightness 0-2: OFF (command: 0x00)
    - brightness 253-255: ON without PWM (command: 0x01)
    - brightness 3-252: PWM dimming (command: 0x11)
    """

    def test_brightness_0_sends_off(self, mock_can_bus, mock_logger):
        """Test brightness 0 sends OFF command (mode byte 0x00)."""
        lights_config = {"test": {"switch_nr": 2, "name": "Test Light"}}
        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.lights["test"].set_brightness(0)

        mock_can_bus.send.assert_called_once()
        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [2, 0x00, 0x00, 0x00]

    def test_brightness_1_sends_off(self, mock_can_bus, mock_logger):
        """Test brightness 1 sends OFF command."""
        lights_config = {"test": {"switch_nr": 2, "name": "Test Light"}}
        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.lights["test"].set_brightness(1)

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [2, 0x00, 0x00, 0x00]

    def test_brightness_2_sends_off(self, mock_can_bus, mock_logger):
        """Test brightness 2 sends OFF command (threshold edge)."""
        lights_config = {"test": {"switch_nr": 2, "name": "Test Light"}}
        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.lights["test"].set_brightness(2)

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [2, 0x00, 0x00, 0x00]

    def test_brightness_3_sends_pwm(self, mock_can_bus, mock_logger):
        """Test brightness 3 sends PWM command (just above threshold)."""
        lights_config = {"test": {"switch_nr": 2, "name": "Test Light"}}
        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.lights["test"].set_brightness(3)

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [2, 0x11, 0x00, 3]

    def test_brightness_128_sends_pwm(self, mock_can_bus, mock_logger):
        """Test brightness 128 sends PWM command."""
        lights_config = {"test": {"switch_nr": 2, "name": "Test Light"}}
        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.lights["test"].set_brightness(128)

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [2, 0x11, 0x00, 128]

    def test_brightness_252_sends_pwm(self, mock_can_bus, mock_logger):
        """Test brightness 252 sends PWM command (just below upper threshold)."""
        lights_config = {"test": {"switch_nr": 2, "name": "Test Light"}}
        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.lights["test"].set_brightness(252)

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [2, 0x11, 0x00, 252]

    def test_brightness_253_sends_on_without_pwm(self, mock_can_bus, mock_logger):
        """Test brightness 253 sends ON command without PWM (upper threshold)."""
        lights_config = {"test": {"switch_nr": 2, "name": "Test Light"}}
        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.lights["test"].set_brightness(253)

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [2, 0x01, 0x00, 0x00]

    def test_brightness_254_sends_on_without_pwm(self, mock_can_bus, mock_logger):
        """Test brightness 254 sends ON command without PWM."""
        lights_config = {"test": {"switch_nr": 2, "name": "Test Light"}}
        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.lights["test"].set_brightness(254)

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [2, 0x01, 0x00, 0x00]

    def test_brightness_255_sends_on_without_pwm(self, mock_can_bus, mock_logger):
        """Test brightness 255 sends ON command without PWM."""
        lights_config = {"test": {"switch_nr": 2, "name": "Test Light"}}
        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.lights["test"].set_brightness(255)

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [2, 0x01, 0x00, 0x00]


class TestBloc9SwitchCommands:
    """Test switch ON/OFF commands."""

    def test_switch_turn_on(self, mock_can_bus, mock_logger):
        """Test switch turn_on sends correct command."""
        switches_config = {"pump": {"switch_nr": 4, "name": "Bilge Pump"}}
        device = Bloc9Device(
            device_id=3,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.switches["pump"].turn_on()

        mock_can_bus.send.assert_called_once()
        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [4, 0x01, 0x00, 0x00]

    def test_switch_turn_off(self, mock_can_bus, mock_logger):
        """Test switch turn_off sends correct command."""
        switches_config = {"pump": {"switch_nr": 4, "name": "Bilge Pump"}}
        device = Bloc9Device(
            device_id=3,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.switches["pump"].turn_on()
        mock_can_bus.send.reset_mock()

        device.switches["pump"].turn_off()

        sent_msg = mock_can_bus.send.call_args[0][0]
        assert list(sent_msg.data) == [4, 0x00, 0x00, 0x00]

    def test_switch_multiple_outputs(self, mock_can_bus, mock_logger):
        """Test multiple switches on same device use correct switch_nr."""
        switches_config = {
            "pump1": {"switch_nr": 0, "name": "Pump 1"},
            "pump2": {"switch_nr": 1, "name": "Pump 2"},
            "pump3": {"switch_nr": 2, "name": "Pump 3"},
        }
        device = Bloc9Device(
            device_id=5,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        device.switches["pump1"].turn_on()
        device.switches["pump2"].turn_on()
        device.switches["pump3"].turn_off()

        assert mock_can_bus.send.call_count == 3
        calls = mock_can_bus.send.call_args_list

        # pump1 ON
        assert list(calls[0][0][0].data) == [0, 0x01, 0x00, 0x00]
        # pump2 ON
        assert list(calls[1][0][0].data) == [1, 0x01, 0x00, 0x00]
        # pump3 OFF
        assert list(calls[2][0][0].data) == [2, 0x00, 0x00, 0x00]


class TestBloc9MessageProcessing:
    """Test CAN message processing and state updates."""

    def test_process_switch_change_s1_s2(
        self, mock_can_bus, mock_logger, mock_can_message
    ):
        """Test processing S1/S2 switch change messages (0x02160600)."""
        lights_config = {
            "s1_light": {"switch_nr": 0, "name": "S1 Light"},
            "s2_light": {"switch_nr": 1, "name": "S2 Light"},
        }
        device = Bloc9Device(
            device_id=10,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        # S1=ON (brightness 150), S2=OFF
        msg = mock_can_message(
            arbitration_id=0x021606D0, data=[0x01, 150, 0x00, 0x00]  # device_id=10
        )

        device.process_message(msg)

        assert device.lights["s1_light"].is_on() is True
        assert device.lights["s1_light"].get_brightness() == 150
        assert device.lights["s2_light"].is_on() is False

    def test_process_switch_change_s3_s4(
        self, mock_can_bus, mock_logger, mock_can_message
    ):
        """Test processing S3/S4 switch change messages (0x02180600)."""
        lights_config = {
            "s3_light": {"switch_nr": 2, "name": "S3 Light"},
            "s4_light": {"switch_nr": 3, "name": "S4 Light"},
        }
        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        # S3=OFF, S4=ON (brightness 200)
        msg = mock_can_message(
            arbitration_id=0x021806B8, data=[0x00, 0x00, 0x01, 200]  # device_id=7
        )

        device.process_message(msg)

        assert device.lights["s3_light"].is_on() is False
        assert device.lights["s4_light"].is_on() is True
        assert device.lights["s4_light"].get_brightness() == 200

    def test_process_switch_change_s5_s6(
        self, mock_can_bus, mock_logger, mock_can_message
    ):
        """Test processing S5/S6 switch change messages (0x021A0600)."""
        switches_config = {
            "s5_switch": {"switch_nr": 4, "name": "S5 Switch"},
            "s6_switch": {"switch_nr": 5, "name": "S6 Switch"},
        }
        device = Bloc9Device(
            device_id=3,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        # S5=ON, S6=OFF
        msg = mock_can_message(
            arbitration_id=0x021A0698, data=[0x01, 0x00, 0x00, 0x00]  # device_id=3
        )

        device.process_message(msg)

        assert device.switches["s5_switch"].is_on() is True
        assert device.switches["s6_switch"].is_on() is False

    def test_process_low_priority_status(
        self, mock_can_bus, mock_logger, mock_can_message
    ):
        """Test processing low-priority status messages (0x00000600)."""
        lights_config = {
            "s1": {"switch_nr": 0, "name": "S1"},
            "s2": {"switch_nr": 1, "name": "S2"},
            "s3": {"switch_nr": 2, "name": "S3"},
        }
        device = Bloc9Device(
            device_id=5,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        # Status: S1=ON (100), S2=OFF, S3=ON (255)
        msg = mock_can_message(
            arbitration_id=0x000006A8,  # device_id=5
            data=[0x01, 100, 0x00, 0x00, 0x01, 255, 0x00, 0x00],
        )

        device.process_message(msg)

        assert device.lights["s1"].is_on() is True
        assert device.lights["s1"].get_brightness() == 100
        assert device.lights["s2"].is_on() is False
        assert device.lights["s3"].is_on() is True
        assert device.lights["s3"].get_brightness() == 255

    def test_ignores_wrong_device_id(self, mock_can_bus, mock_logger, mock_can_message):
        """Test device ignores messages for different device_id."""
        lights_config = {"test": {"switch_nr": 0, "name": "Test"}}
        device = Bloc9Device(
            device_id=3,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        # Message for device_id=5
        msg = mock_can_message(
            arbitration_id=0x021606A8, data=[0x01, 200, 0x00, 0x00]  # device_id=5
        )

        device.process_message(msg)

        # Should not affect device 3
        assert device.lights["test"].is_on() is False


class TestBloc9StatePersistence:
    """Test state save/restore functionality."""

    def test_store_to_state(self, mock_can_bus, mock_logger):
        """Test storing device state."""
        lights_config = {
            "light1": {"switch_nr": 0, "name": "Light 1"},
            "light2": {"switch_nr": 1, "name": "Light 2"},
        }
        switches_config = {"switch1": {"switch_nr": 2, "name": "Switch 1"}}

        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        # Set some states
        device.lights["light1"].set_brightness(150)
        device.lights["light2"].set_brightness(0)
        device.switches["switch1"].turn_on()

        # Store state
        state = device.store_to_state()

        assert state["device_id"] == 7
        assert state["lights"]["light1"]["brightness"] == 150
        assert state["lights"]["light1"]["is_on"] is True
        assert state["lights"]["light2"]["brightness"] == 0
        assert state["lights"]["light2"]["is_on"] is False
        assert state["switches"]["switch1"]["is_on"] is True

    def test_restore_from_state(self, mock_can_bus, mock_logger):
        """Test restoring device state without sending CAN commands."""
        lights_config = {
            "light1": {"switch_nr": 0, "name": "Light 1"},
            "light2": {"switch_nr": 1, "name": "Light 2"},
        }
        switches_config = {"switch1": {"switch_nr": 2, "name": "Switch 1"}}

        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            switches_config=switches_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        state = {
            "device_id": 7,
            "lights": {
                "light1": {"brightness": 200, "is_on": True},
                "light2": {"brightness": 0, "is_on": False},
            },
            "switches": {"switch1": {"is_on": True}},
        }

        # Restore state
        device.restore_from_state(state)

        # Check states restored
        assert device.lights["light1"].get_brightness() == 200
        assert device.lights["light1"].is_on() is True
        assert device.lights["light2"].get_brightness() == 0
        assert device.lights["light2"].is_on() is False
        assert device.switches["switch1"].is_on() is True

        # CRITICAL: Should NOT have sent CAN commands
        mock_can_bus.send.assert_not_called()

    def test_restore_from_state_missing_entities(self, mock_can_bus, mock_logger):
        """Test restoring state with missing entities is handled gracefully."""
        lights_config = {"light1": {"switch_nr": 0, "name": "Light 1"}}

        device = Bloc9Device(
            device_id=7,
            lights_config=lights_config,
            can_bus=mock_can_bus,
            logger=mock_logger,
        )

        state = {
            "device_id": 7,
            "lights": {
                "light1": {"brightness": 100, "is_on": True},
                "nonexistent": {"brightness": 50, "is_on": True},  # Doesn't exist
            },
        }

        # Should not raise exception
        device.restore_from_state(state)

        # Existing light should be restored
        assert device.lights["light1"].get_brightness() == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
