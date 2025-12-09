#!/usr/bin/env python3
"""
Tests for transition cancellation behavior.

These tests ensure that transitions are properly cancelled when new commands arrive,
especially critical for turning off lights while they're transitioning.
"""

import json
import sys
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scheiber" / "src"))

import pytest
from devices import Bloc9, TransitionController


class TestTransitionCancellation:
    """Test that transitions are properly cancelled when new commands arrive."""

    @pytest.fixture
    def mock_mqtt_client(self):
        """Create a mock MQTT client."""
        client = MagicMock()
        client.publish = MagicMock()
        return client

    @pytest.fixture
    def mock_can_bus(self):
        """Create a mock CAN bus."""
        bus = MagicMock()
        bus.send = MagicMock()
        return bus

    @pytest.fixture
    def bloc9_device(self, mock_mqtt_client, mock_can_bus):
        """Create a Bloc9 device for testing."""
        device_config = {
            "name": "Test Bloc9",
            "matchers": [],
        }
        discovery_configs = [
            Mock(
                output="s1",
                component="light",
                entity_id="test_s1",
                name="Test Light",
            )
        ]

        device = Bloc9(
            device_type="bloc9",
            device_id=7,
            device_config=device_config,
            mqtt_client=mock_mqtt_client,
            mqtt_topic_prefix="homeassistant",
            can_bus=mock_can_bus,
            data_dir=None,
            discovery_configs=discovery_configs,
        )

        return device

    def test_immediate_command_cancels_running_transition(
        self, bloc9_device, mock_can_bus
    ):
        """Test that an immediate command cancels a running transition."""
        property_name = "s1"

        # Set initial state to 0 so transition will actually start
        bloc9_device.state[f"{property_name}_brightness"] = 0

        # Start a long transition (5 seconds)
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            json.dumps({"state": "ON", "brightness": 255, "transition": 5}),
        )

        # Wait a bit to let transition start
        time.sleep(0.2)

        # Verify transition is active
        assert property_name in bloc9_device.transition_controller.active_transitions

        # Send immediate OFF command (no transition)
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            json.dumps({"state": "OFF", "brightness": 0}),
        )

        # Verify transition was cancelled immediately
        assert (
            property_name not in bloc9_device.transition_controller.active_transitions
        )

    def test_new_transition_cancels_previous_transition(
        self, bloc9_device, mock_can_bus
    ):
        """Test that starting a new transition cancels the previous one."""
        property_name = "s1"

        # Set initial state to 0
        bloc9_device.state[f"{property_name}_brightness"] = 0

        # Start first transition
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            json.dumps({"state": "ON", "brightness": 255, "transition": 5}),
        )

        time.sleep(0.2)

        # Get the first thread
        first_thread = bloc9_device.transition_controller.active_transitions.get(
            property_name
        )
        assert first_thread is not None

        # Start second transition
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            json.dumps({"state": "ON", "brightness": 128, "transition": 3}),
        )

        time.sleep(0.2)

        # Get the second thread
        second_thread = bloc9_device.transition_controller.active_transitions.get(
            property_name
        )

        # Verify it's a different thread
        assert second_thread is not None
        assert second_thread != first_thread

        # Verify first thread is no longer active
        assert not first_thread.is_alive()

        # Clean up
        bloc9_device.transition_controller.cancel_all()

    def test_off_command_during_fade_up(self, bloc9_device, mock_can_bus):
        """Test turning off a light while it's fading up."""
        property_name = "s1"

        # Start fade up from 0 to 255
        bloc9_device.state[f"{property_name}_brightness"] = 0
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            json.dumps({"state": "ON", "brightness": 255, "transition": 3}),
        )

        time.sleep(0.3)  # Let it fade for 300ms

        # Verify transition is running
        assert property_name in bloc9_device.transition_controller.active_transitions

        # Send immediate OFF
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            json.dumps({"state": "OFF", "brightness": 0}),
        )

        # Verify transition stopped immediately
        assert (
            property_name not in bloc9_device.transition_controller.active_transitions
        )

        # Wait a bit more and ensure no further CAN messages are sent
        initial_send_count = mock_can_bus.send.call_count
        time.sleep(0.5)
        # Should be no new messages (or at most 1 from the OFF command settling)
        assert mock_can_bus.send.call_count <= initial_send_count + 1

    def test_legacy_command_cancels_transition(self, bloc9_device, mock_can_bus):
        """Test that legacy ON/OFF commands cancel transitions."""
        property_name = "s1"

        # Set initial state to 0
        bloc9_device.state[f"{property_name}_brightness"] = 0

        # Start a transition
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            json.dumps({"state": "ON", "brightness": 255, "transition": 5}),
        )

        time.sleep(0.2)
        assert property_name in bloc9_device.transition_controller.active_transitions

        # Send legacy OFF command (plain text, not JSON)
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            "OFF",
        )

        # Verify transition was cancelled
        assert (
            property_name not in bloc9_device.transition_controller.active_transitions
        )

    def test_switch_command_cancels_transition(self, bloc9_device, mock_can_bus):
        """Test that commands to non-light entities also cancel any stray transitions."""
        # Configure s1 as a switch (not a light)
        bloc9_device.discovery_configs = [
            Mock(
                output="s1",
                component="switch",
                entity_id="test_s1",
                name="Test Switch",
            )
        ]

        property_name = "s1"

        # Manually start a transition (shouldn't happen normally for switches)
        bloc9_device.transition_controller.start_transition(
            property_name=property_name,
            switch_nr=0,
            start_brightness=0,
            end_brightness=255,
            duration=5,
        )

        time.sleep(0.2)
        assert property_name in bloc9_device.transition_controller.active_transitions

        # Send switch command
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            "ON",
        )

        # Verify transition was cancelled (safety measure)
        assert (
            property_name not in bloc9_device.transition_controller.active_transitions
        )


class TestTransitionControllerCancellation:
    """Test TransitionController cancellation methods directly."""

    @pytest.fixture
    def mock_device(self):
        """Create a mock device with _send_switch_command method."""
        device = Mock()
        device._send_switch_command = Mock()
        device.logger = MagicMock()
        return device

    @pytest.fixture
    def controller(self, mock_device):
        """Create a TransitionController."""
        return TransitionController(mock_device, step_delay=0.05)

    def test_cancel_transition_stops_thread(self, controller, mock_device):
        """Test that cancel_transition stops the thread."""
        # Start a transition
        controller.start_transition(
            property_name="s1",
            switch_nr=0,
            start_brightness=0,
            end_brightness=255,
            duration=5,
        )

        time.sleep(0.1)
        assert "s1" in controller.active_transitions

        # Cancel it
        controller.cancel_transition("s1")

        # Verify it's stopped
        assert "s1" not in controller.active_transitions
        assert "s1" not in controller.stop_events

    def test_cancel_nonexistent_transition(self, controller):
        """Test that cancelling a non-existent transition doesn't error."""
        # Should not raise an exception
        controller.cancel_transition("nonexistent")

    def test_cancel_all_stops_multiple_transitions(self, controller, mock_device):
        """Test that cancel_all stops all active transitions."""
        # Start multiple transitions
        for i in range(1, 4):
            controller.start_transition(
                property_name=f"s{i}",
                switch_nr=i - 1,
                start_brightness=0,
                end_brightness=255,
                duration=5,
            )

        time.sleep(0.1)
        assert len(controller.active_transitions) == 3

        # Cancel all
        controller.cancel_all()

        # Verify all stopped
        assert len(controller.active_transitions) == 0
        assert len(controller.stop_events) == 0

    def test_transition_stops_on_cancel_signal(self, controller, mock_device):
        """Test that transition loop exits when stop event is set."""
        # Start a long transition
        controller.start_transition(
            property_name="s1",
            switch_nr=0,
            start_brightness=0,
            end_brightness=255,
            duration=10,  # Very long
        )

        time.sleep(0.2)  # Let a few steps execute
        initial_call_count = mock_device._send_switch_command.call_count

        # Cancel it
        controller.cancel_transition("s1")

        # Wait a bit and verify no more commands are sent
        time.sleep(0.3)
        assert mock_device._send_switch_command.call_count == initial_call_count


class TestCriticalSafetyScenarios:
    """Test critical safety scenarios to ensure lights can always be turned off."""

    @pytest.fixture
    def mock_mqtt_client(self):
        """Create a mock MQTT client."""
        client = MagicMock()
        client.publish = MagicMock()
        return client

    @pytest.fixture
    def mock_can_bus(self):
        """Create a mock CAN bus."""
        bus = MagicMock()
        bus.send = MagicMock()
        return bus

    @pytest.fixture
    def bloc9_device(self, mock_mqtt_client, mock_can_bus):
        """Create a Bloc9 device for testing."""
        device_config = {
            "name": "Test Bloc9",
            "matchers": [],
        }
        discovery_configs = [
            Mock(
                output="s1",
                component="light",
                entity_id="test_s1",
                name="Test Light",
            )
        ]

        device = Bloc9(
            device_type="bloc9",
            device_id=7,
            device_config=device_config,
            mqtt_client=mock_mqtt_client,
            mqtt_topic_prefix="homeassistant",
            can_bus=mock_can_bus,
            data_dir=None,
            discovery_configs=discovery_configs,
        )

        return device

    def test_multiple_rapid_commands(self, bloc9_device, mock_can_bus):
        """Test rapid command changes don't leave orphaned transitions."""
        property_name = "s1"

        # Send multiple commands rapidly
        commands = [
            {"state": "ON", "brightness": 255, "transition": 2},
            {"state": "ON", "brightness": 128, "transition": 1},
            {"state": "OFF", "brightness": 0},
            {"state": "ON", "brightness": 200, "transition": 3},
            {"state": "OFF", "brightness": 0},
        ]

        for cmd in commands:
            bloc9_device.handle_command(
                "homeassistant/scheiber/bloc9/7/s1/set",
                json.dumps(cmd),
            )
            time.sleep(0.05)  # Small delay between commands

        # Wait for any transitions to settle
        time.sleep(0.2)

        # Verify at most one transition is active (the last one with transition>0)
        # Or zero if the final OFF command already completed
        assert len(bloc9_device.transition_controller.active_transitions) <= 1

        # Clean up any remaining transition
        bloc9_device.transition_controller.cancel_all()

    def test_guaranteed_off_state(self, bloc9_device, mock_can_bus):
        """Test that OFF command is guaranteed to turn light off, even during transition."""
        property_name = "s1"

        # Start long fade up
        bloc9_device.state[f"{property_name}_brightness"] = 0
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            json.dumps({"state": "ON", "brightness": 255, "transition": 10}),
        )

        time.sleep(0.3)

        # Send OFF command
        bloc9_device.handle_command(
            "homeassistant/scheiber/bloc9/7/s1/set",
            json.dumps({"state": "OFF", "brightness": 0}),
        )

        # Verify the OFF command was sent to CAN bus
        # Look for the OFF command in the calls
        off_command_sent = False
        for call_args in mock_can_bus.send.call_args_list:
            msg = call_args[0][0]
            if len(msg.data) >= 2 and msg.data[0] == 0 and msg.data[1] == 0x00:
                off_command_sent = True
                break

        assert off_command_sent, "OFF command should be sent to CAN bus"

        # Verify no transition is running
        assert (
            property_name not in bloc9_device.transition_controller.active_transitions
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
