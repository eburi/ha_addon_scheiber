"""
Test switch state updates with CAN confirmation.

Verifies that switches wait for CAN confirmation before publishing state to MQTT.
"""

import json
import time
from unittest.mock import Mock, MagicMock, call
import pytest
import can

from can_mqtt_bridge.bridge import MQTTBridge
from can_mqtt_bridge.switch import MQTTSwitch
from scheiber import create_scheiber_system
from scheiber.switch import Switch
from scheiber.bloc9 import Bloc9Device


class TestSwitchStateConfirmation:
    """Test that switches wait for CAN confirmation before updating MQTT state."""

    def test_switch_waits_for_can_confirmation(self):
        """
        Test full flow: MQTT command -> CAN command -> CAN confirmation -> MQTT state update.

        This ensures Home Assistant sees the actual hardware state, not optimistic updates.
        """
        # Setup mock CAN bus
        mock_can_bus = Mock()
        mock_can_bus.send_message = Mock()

        # Create Bloc9 device with a switch
        device = Bloc9Device(
            device_id=10,
            can_bus=mock_can_bus,
            switches_config={"s3": {"name": "Test Switch", "entity_id": "test_switch"}},
        )

        switch = device.switches[0]  # S3 switch
        assert switch.get_state() == False  # Initially OFF

        # Setup MQTT mock
        mock_mqtt_client = Mock()
        mock_mqtt_client.publish = Mock()

        # Create MQTT switch entity
        mqtt_switch = MQTTSwitch(
            hardware_switch=switch,
            device_type="bloc9",
            device_id=10,
            mqtt_client=mock_mqtt_client,
            mqtt_topic_prefix="homeassistant",
        )

        # Reset mock to clear initial state publish
        mock_mqtt_client.publish.reset_mock()

        # Step 1: Receive MQTT command to turn ON
        mqtt_switch.handle_command("ON")

        # Verify: CAN command was sent
        mock_can_bus.send_message.assert_called_once()
        can_id, data = mock_can_bus.send_message.call_args[0]
        assert can_id == 0x023606D0  # Bloc9 ID=10, command
        assert data == bytes([0x02, 0x01, 0x00, 0x00])  # S3=ON

        # Verify: Switch internal state is still OFF (waiting for confirmation)
        assert switch.get_state() == False

        # Verify: NO MQTT state update yet (waiting for CAN confirmation)
        assert mock_mqtt_client.publish.call_count == 0

        # Step 2: Simulate CAN confirmation message from hardware
        # S3/S4 state change message with S3=ON
        can_confirmation = can.Message(
            arbitration_id=0x021806D0,  # S3/S4 state change for device 10
            data=bytes([0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00]),  # S3=ON
            is_extended_id=True,
        )

        # Process the CAN message
        device.process_message(can_confirmation)

        # Verify: Switch internal state is now ON
        assert switch.get_state() == True

        # Verify: MQTT state was published ONLY AFTER CAN confirmation
        assert mock_mqtt_client.publish.call_count == 1
        publish_call = mock_mqtt_client.publish.call_args
        assert publish_call[0][0] == "homeassistant/scheiber/bloc9/10/s3/state"
        assert publish_call[0][1] == "ON"
        assert publish_call[1]["retain"] == True

    def test_switch_physical_button_updates_mqtt(self):
        """
        Test that physical button presses update MQTT state.

        When someone presses a button on the boat panel:
        1. CAN message arrives with new state
        2. Switch updates internal state
        3. MQTT state is published
        """
        # Setup mock CAN bus
        mock_can_bus = Mock()

        # Create Bloc9 device with a switch
        device = Bloc9Device(
            device_id=10,
            can_bus=mock_can_bus,
            switches_config={"s3": {"name": "Test Switch", "entity_id": "test_switch"}},
        )

        switch = device.switches[0]
        assert switch.get_state() == False

        # Setup MQTT mock
        mock_mqtt_client = Mock()

        # Create MQTT switch entity
        mqtt_switch = MQTTSwitch(
            hardware_switch=switch,
            device_type="bloc9",
            device_id=10,
            mqtt_client=mock_mqtt_client,
            mqtt_topic_prefix="homeassistant",
        )

        # Reset mock to clear initial state publish
        mock_mqtt_client.publish.reset_mock()

        # Simulate physical button press - CAN message arrives
        can_state_change = can.Message(
            arbitration_id=0x021806D0,  # S3/S4 state change
            data=bytes([0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00]),  # S3=ON
            is_extended_id=True,
        )

        device.process_message(can_state_change)

        # Verify: Switch state updated
        assert switch.get_state() == True

        # Verify: MQTT state published
        assert mock_mqtt_client.publish.call_count == 1
        publish_call = mock_mqtt_client.publish.call_args
        assert publish_call[0][0] == "homeassistant/scheiber/bloc9/10/s3/state"
        assert publish_call[0][1] == "ON"

    def test_switch_turn_off_flow(self):
        """Test turning OFF also waits for CAN confirmation."""
        # Setup
        mock_can_bus = Mock()
        device = Bloc9Device(
            device_id=10,
            can_bus=mock_can_bus,
            switches_config={"s3": {"name": "Test Switch", "entity_id": "test_switch"}},
        )

        switch = device.switches[0]

        # Start with switch ON
        switch.update_state(True)
        assert switch.get_state() == True

        # Setup MQTT
        mock_mqtt_client = Mock()
        mqtt_switch = MQTTSwitch(
            hardware_switch=switch,
            device_type="bloc9",
            device_id=10,
            mqtt_client=mock_mqtt_client,
            mqtt_topic_prefix="homeassistant",
        )
        mock_mqtt_client.publish.reset_mock()

        # Send OFF command
        mqtt_switch.handle_command("OFF")

        # Verify: CAN command sent
        mock_can_bus.send_message.assert_called_once()
        can_id, data = mock_can_bus.send_message.call_args[0]
        assert data == bytes([0x02, 0x00, 0x00, 0x00])  # S3=OFF

        # Verify: State still ON (waiting for confirmation)
        assert switch.get_state() == True

        # Verify: No MQTT update yet
        assert mock_mqtt_client.publish.call_count == 0

        # Simulate CAN confirmation
        can_confirmation = can.Message(
            arbitration_id=0x021806D0,
            data=bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # S3=OFF
            is_extended_id=True,
        )
        device.process_message(can_confirmation)

        # Verify: State now OFF
        assert switch.get_state() == False

        # Verify: MQTT updated
        assert mock_mqtt_client.publish.call_count == 1
        assert mock_mqtt_client.publish.call_args[0][1] == "OFF"

    def test_mqtt_discovery_optimistic_false(self):
        """Verify discovery config has optimistic=False."""
        mock_can_bus = Mock()
        device = Bloc9Device(
            device_id=10,
            can_bus=mock_can_bus,
            switches_config={"s3": {"name": "Test Switch", "entity_id": "test_switch"}},
        )

        mock_mqtt_client = Mock()
        mqtt_switch = MQTTSwitch(
            hardware_switch=device.switches[0],
            device_type="bloc9",
            device_id=10,
            mqtt_client=mock_mqtt_client,
            mqtt_topic_prefix="homeassistant",
        )

        # Publish discovery
        mqtt_switch.publish_discovery()

        # Get the discovery config
        publish_call = mock_mqtt_client.publish.call_args
        config_json = publish_call[0][1]
        config = json.loads(config_json)

        # Verify optimistic is False
        assert config["optimistic"] == False

        # Verify payload format
        assert config["payload_on"] == "ON"
        assert config["payload_off"] == "OFF"
        assert config["state_on"] == "ON"
        assert config["state_off"] == "OFF"
