"""
Test retained message handling in MQTT bridge.

Verifies that:
1. Old retained messages (>5 minutes) are ignored
2. Recent retained messages are processed
3. Retained commands are cleared after execution
"""

import time
from unittest.mock import Mock, MagicMock, patch
import pytest

from can_mqtt_bridge.light import MQTTLight
from can_mqtt_bridge.switch import MQTTSwitch


class TestRetainedMessageHandling:
    """Test retained message validation and clearing."""

    def test_light_ignores_old_retained_message(self):
        """Test that old retained messages are ignored."""
        # Setup
        mock_hardware = Mock()
        mock_hardware.switch_nr = 4  # S5 (0-indexed)
        mock_hardware.name = "Test Light"
        mock_hardware.entity_id = "test_light"
        mock_hardware.subscribe = Mock()

        mock_mqtt = Mock()

        light = MQTTLight(
            hardware_light=mock_hardware,
            device_type="bloc9",
            device_id=7,
            mqtt_client=mock_mqtt,
            mqtt_topic_prefix="homeassistant",
            read_only=False,
        )  # Simulate old retained message (6 minutes old)
        old_timestamp = time.time() - 360
        light.handle_command(
            payload='{"state": "ON"}', is_retained=True, timestamp=old_timestamp
        )

        # Verify: hardware command NOT sent
        mock_hardware.set_brightness.assert_not_called()

        # Verify: old retained message is cleared
        mock_mqtt.publish.assert_called_with(light.command_topic, None, retain=True)

    def test_light_processes_recent_retained_message(self):
        """Test that recent retained messages are processed."""
        # Setup
        mock_hardware = Mock()
        mock_hardware.switch_nr = 4  # S5 (0-indexed)
        mock_hardware.name = "Test Light"
        mock_hardware.entity_id = "test_light"
        mock_hardware.subscribe = Mock()

        mock_mqtt = Mock()

        light = MQTTLight(
            hardware_light=mock_hardware,
            device_type="bloc9",
            device_id=7,
            mqtt_client=mock_mqtt,
            mqtt_topic_prefix="homeassistant",
            read_only=False,
        )  # Simulate recent retained message (1 minute old)
        recent_timestamp = time.time() - 60
        light.handle_command(
            payload='{"state": "ON"}', is_retained=True, timestamp=recent_timestamp
        )

        # Verify: hardware command IS sent
        mock_hardware.set_brightness.assert_called_once_with(255)

        # Verify: retained message is cleared after execution
        mock_mqtt.publish.assert_called_with(light.command_topic, None, retain=True)

    def test_light_processes_non_retained_message(self):
        """Test that non-retained messages are processed normally."""
        # Setup
        mock_hardware = Mock()
        mock_hardware.switch_nr = 4  # S5 (0-indexed)
        mock_hardware.name = "Test Light"
        mock_hardware.entity_id = "test_light"
        mock_hardware.subscribe = Mock()

        mock_mqtt = Mock()

        light = MQTTLight(
            hardware_light=mock_hardware,
            device_type="bloc9",
            device_id=7,
            mqtt_client=mock_mqtt,
            mqtt_topic_prefix="homeassistant",
            read_only=False,
        )  # Simulate non-retained message
        light.handle_command(
            payload='{"state": "ON"}', is_retained=False, timestamp=None
        )

        # Verify: hardware command IS sent
        mock_hardware.set_brightness.assert_called_once_with(255)

        # Verify: NO clearing (not retained)
        mock_mqtt.publish.assert_not_called()

    def test_switch_ignores_old_retained_message(self):
        """Test that switches ignore old retained messages."""
        # Setup
        mock_hardware = Mock()
        mock_hardware.switch_nr = 4  # S5 (0-indexed)
        mock_hardware.name = "Test Switch"
        mock_hardware.entity_id = "test_switch"
        mock_hardware.subscribe = Mock()

        mock_mqtt = Mock()

        switch = MQTTSwitch(
            hardware_switch=mock_hardware,
            device_type="bloc9",
            device_id=7,
            mqtt_client=mock_mqtt,
            mqtt_topic_prefix="homeassistant",
            read_only=False,
        )  # Simulate old retained message (6 minutes old)
        old_timestamp = time.time() - 360
        switch.handle_command(
            payload='{"state": "ON"}', is_retained=True, timestamp=old_timestamp
        )

        # Verify: hardware command NOT sent
        mock_hardware.set.assert_not_called()

        # Verify: old retained message is cleared
        mock_mqtt.publish.assert_called_with(switch.command_topic, None, retain=True)

    def test_switch_processes_recent_retained_message(self):
        """Test that switches process recent retained messages."""
        # Setup
        mock_hardware = Mock()
        mock_hardware.switch_nr = 4  # S5 (0-indexed)
        mock_hardware.name = "Test Switch"
        mock_hardware.entity_id = "test_switch"
        mock_hardware.subscribe = Mock()

        mock_mqtt = Mock()

        switch = MQTTSwitch(
            hardware_switch=mock_hardware,
            device_type="bloc9",
            device_id=7,
            mqtt_client=mock_mqtt,
            mqtt_topic_prefix="homeassistant",
            read_only=False,
        )  # Simulate recent retained message (1 minute old)
        recent_timestamp = time.time() - 60
        switch.handle_command(
            payload="ON", is_retained=True, timestamp=recent_timestamp
        )

        # Verify: hardware command IS sent
        mock_hardware.set.assert_called_once_with(True)

        # Verify: retained message is cleared after execution
        mock_mqtt.publish.assert_called_with(switch.command_topic, None, retain=True)

    def test_switch_processes_non_retained_message(self):
        """Test that switches process non-retained messages normally."""
        # Setup
        mock_hardware = Mock()
        mock_hardware.switch_nr = 4  # S5 (0-indexed)
        mock_hardware.name = "Test Switch"
        mock_hardware.entity_id = "test_switch"
        mock_hardware.subscribe = Mock()

        mock_mqtt = Mock()

        switch = MQTTSwitch(
            hardware_switch=mock_hardware,
            device_type="bloc9",
            device_id=7,
            mqtt_client=mock_mqtt,
            mqtt_topic_prefix="homeassistant",
            read_only=False,
        )  # Simulate non-retained message
        switch.handle_command(payload="ON", is_retained=False, timestamp=None)

        # Verify: hardware command IS sent
        mock_hardware.set.assert_called_once_with(True)

        # Verify: NO clearing (not retained)
        mock_mqtt.publish.assert_not_called()

    def test_age_threshold_just_under_5_minutes(self):
        """Test boundary: just under 5 minutes should be processed."""
        # Setup
        mock_hardware = Mock()
        mock_hardware.switch_nr = 4  # S5 (0-indexed)
        mock_hardware.name = "Test Light"
        mock_hardware.entity_id = "test_light"
        mock_hardware.subscribe = Mock()

        mock_mqtt = Mock()

        light = MQTTLight(
            hardware_light=mock_hardware,
            device_type="bloc9",
            device_id=7,
            mqtt_client=mock_mqtt,
            mqtt_topic_prefix="homeassistant",
            read_only=False,
        )  # Simulate message just under 5 minutes old (299 seconds)
        boundary_timestamp = time.time() - 299
        light.handle_command(
            payload='{"state": "ON"}', is_retained=True, timestamp=boundary_timestamp
        )

        # Verify: should be processed (not > 300)
        mock_hardware.set_brightness.assert_called_once_with(255)

    def test_age_threshold_just_over_5_minutes(self):
        """Test boundary: just over 5 minutes should be ignored."""
        # Setup
        mock_hardware = Mock()
        mock_hardware.switch_nr = 4  # S5 (0-indexed)
        mock_hardware.name = "Test Light"
        mock_hardware.entity_id = "test_light"
        mock_hardware.subscribe = Mock()

        mock_mqtt = Mock()

        light = MQTTLight(
            hardware_light=mock_hardware,
            device_type="bloc9",
            device_id=7,
            mqtt_client=mock_mqtt,
            mqtt_topic_prefix="homeassistant",
            read_only=False,
        )  # Simulate message just over 5 minutes old (301 seconds)
        boundary_timestamp = time.time() - 301
        light.handle_command(
            payload='{"state": "ON"}', is_retained=True, timestamp=boundary_timestamp
        )

        # Verify: should be ignored (> 300)
        mock_hardware.set_brightness.assert_not_called()
