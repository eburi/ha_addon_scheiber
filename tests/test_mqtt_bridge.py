#!/usr/bin/env python3
"""
Test cases for MQTTBridge class.
Tests device registration, topic routing, and MQTT command handling.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scheiber", "src"))

import json
import unittest
from unittest.mock import MagicMock, Mock, call, patch

import can

from mqtt_bridge import MQTTBridge


class TestMQTTBridgeInit(unittest.TestCase):
    """Test MQTTBridge initialization."""

    def test_initialization_defaults(self):
        """Test bridge initializes with default values."""
        bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="test_user",
            mqtt_password="test_pass",
            can_interface="can0",
        )

        self.assertEqual(bridge.mqtt_host, "localhost")
        self.assertEqual(bridge.mqtt_port, 1883)
        self.assertEqual(bridge.mqtt_user, "test_user")
        self.assertEqual(bridge.mqtt_password, "test_pass")
        self.assertEqual(bridge.can_interface, "can0")
        self.assertEqual(bridge.mqtt_topic_prefix, "homeassistant")
        self.assertEqual(bridge.log_level, "info")

    def test_initialization_custom_values(self):
        """Test bridge initializes with custom values."""
        bridge = MQTTBridge(
            mqtt_host="mqtt.example.com",
            mqtt_user="admin",
            mqtt_password="secret",
            can_interface="can1",
            mqtt_port=8883,
            mqtt_topic_prefix="boat",
            log_level="debug",
        )

        self.assertEqual(bridge.mqtt_host, "mqtt.example.com")
        self.assertEqual(bridge.mqtt_port, 8883)
        self.assertEqual(bridge.mqtt_topic_prefix, "boat")
        self.assertEqual(bridge.log_level, "debug")

    def test_topic_prefix_trailing_slash_stripped(self):
        """Test that trailing slashes are stripped from topic prefix."""
        bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="user",
            mqtt_password="pass",
            can_interface="can0",
            mqtt_topic_prefix="homeassistant/",
        )

        self.assertEqual(bridge.mqtt_topic_prefix, "homeassistant")

    def test_initial_state(self):
        """Test that bridge starts with empty tracking structures."""
        bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="user",
            mqtt_password="pass",
            can_interface="can0",
        )

        self.assertIsNone(bridge.can_bus)
        self.assertIsNone(bridge.mqtt_client)
        self.assertEqual(bridge.devices, {})
        self.assertEqual(bridge.topic_handlers, {})
        self.assertEqual(bridge.last_seen, {})
        self.assertEqual(len(bridge.bus_stats["unique_sender_ids"]), 0)
        self.assertEqual(bridge.bus_stats["total_messages"], 0)


class TestMQTTBridgeConnection(unittest.TestCase):
    """Test MQTT and CAN connection handling."""

    @patch("mqtt_bridge.mqtt.Client")
    def test_connect_mqtt(self, mock_mqtt_client):
        """Test MQTT connection setup."""
        mock_client_instance = MagicMock()
        mock_mqtt_client.return_value = mock_client_instance

        bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="test_user",
            mqtt_password="test_pass",
            can_interface="can0",
        )
        bridge.connect_mqtt()

        # Verify client was created
        mock_mqtt_client.assert_called_once()

        # Verify callbacks were set
        self.assertEqual(bridge.mqtt_client.on_connect, bridge.on_mqtt_connect)
        self.assertEqual(bridge.mqtt_client.on_disconnect, bridge.on_mqtt_disconnect)
        self.assertEqual(bridge.mqtt_client.on_message, bridge.on_mqtt_message)

        # Verify connection was established
        mock_client_instance.username_pw_set.assert_called_once_with(
            "test_user", "test_pass"
        )
        mock_client_instance.connect.assert_called_once_with(
            "localhost", 1883, keepalive=60
        )
        mock_client_instance.loop_start.assert_called_once()

    @patch("mqtt_bridge.can.interface.Bus")
    def test_connect_can(self, mock_can_bus):
        """Test CAN bus connection setup."""
        mock_bus_instance = MagicMock()
        mock_can_bus.return_value = mock_bus_instance

        bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="user",
            mqtt_password="pass",
            can_interface="can1",
        )
        bridge.connect_can()

        # Verify bus was opened
        mock_can_bus.assert_called_once_with(channel="can1", interface="socketcan")
        self.assertEqual(bridge.can_bus, mock_bus_instance)


class TestMQTTCallbacks(unittest.TestCase):
    """Test MQTT callback handlers."""

    def setUp(self):
        """Set up test bridge."""
        self.bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="user",
            mqtt_password="pass",
            can_interface="can0",
        )

    def test_on_mqtt_connect_success(self):
        """Test successful MQTT connection callback."""
        mock_client = MagicMock()

        self.bridge.on_mqtt_connect(mock_client, None, None, 0, None)

        # Should not subscribe to anything initially (devices register their own topics)
        mock_client.subscribe.assert_not_called()

    def test_on_mqtt_connect_with_existing_handlers(self):
        """Test MQTT reconnection re-subscribes to existing topics."""
        mock_client = MagicMock()

        # Simulate existing topic handlers
        mock_device = MagicMock()
        mock_handler = MagicMock()
        self.bridge.topic_handlers = {
            "homeassistant/scheiber/bloc9/10/s1/set": (mock_device, mock_handler),
            "homeassistant/scheiber/bloc9/10/s2/set": (mock_device, mock_handler),
        }

        self.bridge.on_mqtt_connect(mock_client, None, None, 0, None)

        # Should re-subscribe to all registered topics
        self.assertEqual(mock_client.subscribe.call_count, 2)

    def test_on_mqtt_connect_failure(self):
        """Test failed MQTT connection callback."""
        mock_client = MagicMock()

        self.bridge.on_mqtt_connect(mock_client, None, None, 5, None)

        # Should not attempt to subscribe on failure
        mock_client.subscribe.assert_not_called()

    def test_on_mqtt_disconnect_expected(self):
        """Test expected MQTT disconnection."""
        mock_client = MagicMock()

        # reason_code 0 = normal disconnect
        self.bridge.on_mqtt_disconnect(mock_client, None, None, 0, None)
        # Should log info, not warning (tested via logs if needed)

    def test_on_mqtt_disconnect_unexpected(self):
        """Test unexpected MQTT disconnection."""
        mock_client = MagicMock()

        # reason_code != 0 = unexpected disconnect
        self.bridge.on_mqtt_disconnect(mock_client, None, None, 1, None)
        # Should log warning (tested via logs if needed)


class TestTopicRouting(unittest.TestCase):
    """Test MQTT topic routing to device handlers."""

    def setUp(self):
        """Set up test bridge."""
        self.bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="user",
            mqtt_password="pass",
            can_interface="can0",
        )

    def test_on_mqtt_message_routes_to_handler(self):
        """Test that messages are routed to registered handlers."""
        # Create mock device and handler
        mock_device = MagicMock()
        mock_handler = MagicMock()

        topic = "homeassistant/scheiber/bloc9/10/s1/set"
        self.bridge.topic_handlers[topic] = (mock_device, mock_handler)

        # Create mock MQTT message
        mock_msg = MagicMock()
        mock_msg.topic = topic
        mock_msg.payload.decode.return_value = "ON"

        # Call the message handler
        self.bridge.on_mqtt_message(None, None, mock_msg)

        # Verify handler was called with correct arguments
        mock_handler.assert_called_once_with(topic, "ON")

    def test_on_mqtt_message_unknown_topic(self):
        """Test handling of messages on unknown topics."""
        # Create mock MQTT message for unregistered topic
        mock_msg = MagicMock()
        mock_msg.topic = "unknown/topic"
        mock_msg.payload.decode.return_value = "test"

        # Should log warning but not crash
        self.bridge.on_mqtt_message(None, None, mock_msg)
        # No assertion needed - just verify it doesn't raise

    def test_on_mqtt_message_handler_exception(self):
        """Test that handler exceptions are caught and logged."""
        # Create mock device and handler that raises exception
        mock_device = MagicMock()
        mock_handler = MagicMock(side_effect=ValueError("Test error"))

        topic = "homeassistant/scheiber/bloc9/10/s1/set"
        self.bridge.topic_handlers[topic] = (mock_device, mock_handler)

        # Create mock MQTT message
        mock_msg = MagicMock()
        mock_msg.topic = topic
        mock_msg.payload.decode.return_value = "ON"

        # Should catch exception and log error, not crash
        self.bridge.on_mqtt_message(None, None, mock_msg)
        # No assertion needed - just verify it doesn't raise

    def test_multiple_devices_registered(self):
        """Test that multiple devices can register different topics."""
        # Create two mock devices with handlers
        mock_device1 = MagicMock()
        mock_handler1 = MagicMock()
        mock_device2 = MagicMock()
        mock_handler2 = MagicMock()

        topic1 = "homeassistant/scheiber/bloc9/10/s1/set"
        topic2 = "homeassistant/scheiber/bloc9/11/s1/set"

        self.bridge.topic_handlers[topic1] = (mock_device1, mock_handler1)
        self.bridge.topic_handlers[topic2] = (mock_device2, mock_handler2)

        # Send message to first device
        mock_msg1 = MagicMock()
        mock_msg1.topic = topic1
        mock_msg1.payload.decode.return_value = "ON"
        self.bridge.on_mqtt_message(None, None, mock_msg1)

        # Verify only handler1 was called
        mock_handler1.assert_called_once_with(topic1, "ON")
        mock_handler2.assert_not_called()

        # Send message to second device
        mock_msg2 = MagicMock()
        mock_msg2.topic = topic2
        mock_msg2.payload.decode.return_value = "OFF"
        self.bridge.on_mqtt_message(None, None, mock_msg2)

        # Verify handler2 was called
        mock_handler2.assert_called_once_with(topic2, "OFF")


class TestBusStatistics(unittest.TestCase):
    """Test CAN bus statistics tracking."""

    def setUp(self):
        """Set up test bridge."""
        self.bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="user",
            mqtt_password="pass",
            can_interface="can0",
        )
        self.bridge.mqtt_client = MagicMock()

    def test_update_bus_statistics_known_device(self):
        """Test statistics update for known device."""
        arb_id = 0x000006C0  # bloc9 bus_id=8

        self.bridge.update_bus_statistics(arb_id, is_known_device=True)

        self.assertEqual(self.bridge.bus_stats["total_messages"], 1)
        self.assertIn(0xC0, self.bridge.bus_stats["unique_sender_ids"])
        self.assertIn(0xC0, self.bridge.bus_stats["known_sender_ids"])

    def test_update_bus_statistics_unknown_device(self):
        """Test statistics update for unknown device."""
        arb_id = 0x12345678

        self.bridge.update_bus_statistics(arb_id, is_known_device=False)

        self.assertEqual(self.bridge.bus_stats["total_messages"], 1)
        self.assertIn(0x78, self.bridge.bus_stats["unique_sender_ids"])
        self.assertNotIn(0x78, self.bridge.bus_stats["known_sender_ids"])

    def test_update_bus_statistics_multiple_messages(self):
        """Test statistics tracking across multiple messages."""
        arb_id1 = 0x000006C0  # sender 0xC0
        arb_id2 = 0x000006D0  # sender 0xD0
        arb_id3 = 0x000006C0  # sender 0xC0 again

        self.bridge.update_bus_statistics(arb_id1, is_known_device=True)
        self.bridge.update_bus_statistics(arb_id2, is_known_device=True)
        self.bridge.update_bus_statistics(arb_id3, is_known_device=True)

        self.assertEqual(self.bridge.bus_stats["total_messages"], 3)
        self.assertEqual(len(self.bridge.bus_stats["unique_sender_ids"]), 2)
        self.assertIn(0xC0, self.bridge.bus_stats["unique_sender_ids"])
        self.assertIn(0xD0, self.bridge.bus_stats["unique_sender_ids"])

    def test_publish_bus_statistics(self):
        """Test bus statistics publishing to MQTT."""
        # Add some test data
        self.bridge.bus_stats["unique_sender_ids"].add(0xC0)
        self.bridge.bus_stats["unique_sender_ids"].add(0xD0)
        self.bridge.bus_stats["known_sender_ids"].add(0xC0)
        self.bridge.bus_stats["total_messages"] = 10

        self.bridge.publish_bus_statistics()

        # Verify publish was called
        self.bridge.mqtt_client.publish.assert_called_once()

        # Verify topic
        call_args = self.bridge.mqtt_client.publish.call_args
        topic = call_args[0][0]
        self.assertEqual(topic, "homeassistant/scheiber")

        # Verify payload structure
        payload = json.loads(call_args[0][1])
        self.assertIn("bus_load", payload)
        self.assertIn("messages_per_minute", payload)
        self.assertIn("total_messages", payload)
        self.assertIn("unique_sender_ids", payload)
        self.assertIn("known_sender_ids", payload)
        self.assertEqual(payload["total_messages"], 10)
        self.assertEqual(payload["unique_sender_ids"], 2)
        self.assertEqual(payload["known_sender_ids"], 1)

    def test_publish_bus_statistics_only_on_change(self):
        """Test that statistics are only published when changed."""
        self.bridge.bus_stats["total_messages"] = 5

        # First publish
        self.bridge.publish_bus_statistics()
        self.assertEqual(self.bridge.mqtt_client.publish.call_count, 1)

        # Second publish with no changes
        self.bridge.publish_bus_statistics()
        # Should still be 1 (no additional publish)
        self.assertEqual(self.bridge.mqtt_client.publish.call_count, 1)

        # Change statistics and publish again
        self.bridge.bus_stats["total_messages"] = 10
        self.bridge.publish_bus_statistics()
        # Should now be 2
        self.assertEqual(self.bridge.mqtt_client.publish.call_count, 2)


class TestDeviceRegistration(unittest.TestCase):
    """Test device creation and topic registration."""

    @patch("mqtt_bridge.create_device")
    @patch("mqtt_bridge.can.interface.Bus")
    @patch("mqtt_bridge.mqtt.Client")
    def test_device_registration_on_first_message(
        self, mock_mqtt_client, mock_can_bus, mock_create_device
    ):
        """Test that devices register topics when first seen."""
        # Set up mocks
        mock_mqtt_instance = MagicMock()
        mock_mqtt_client.return_value = mock_mqtt_instance
        mock_can_instance = MagicMock()
        mock_can_bus.return_value = mock_can_instance

        # Create mock device with command topics
        mock_device = MagicMock()
        mock_handler = MagicMock()
        mock_device.register_command_topics.return_value = [
            ("homeassistant/scheiber/bloc9/10/s1/set", mock_handler),
            ("homeassistant/scheiber/bloc9/10/s1/set_brightness", mock_handler),
        ]
        mock_create_device.return_value = mock_device

        # Create bridge
        bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="user",
            mqtt_password="pass",
            can_interface="can0",
        )
        bridge.connect_mqtt()
        bridge.connect_can()

        # Simulate receiving a CAN message from bloc9 bus_id=10
        mock_msg = MagicMock()
        mock_msg.arbitration_id = 0x000006D0  # bloc9 status, bus_id=10
        mock_msg.data = bytes([0x00] * 8)
        mock_can_instance.recv.side_effect = [mock_msg, None]

        # Run one iteration (will break after None)
        try:
            bridge.run()
        except:
            pass  # Expected to exit on None or timeout

        # Verify device was created
        mock_create_device.assert_called_once()

        # Verify topics were registered
        self.assertEqual(len(bridge.topic_handlers), 2)
        self.assertIn("homeassistant/scheiber/bloc9/10/s1/set", bridge.topic_handlers)

        # Verify MQTT subscriptions were made
        self.assertEqual(mock_mqtt_instance.subscribe.call_count, 2)


class TestCleanup(unittest.TestCase):
    """Test resource cleanup."""

    def test_cleanup_mqtt_client(self):
        """Test MQTT client cleanup."""
        bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="user",
            mqtt_password="pass",
            can_interface="can0",
        )

        # Mock MQTT client
        mock_client = MagicMock()
        bridge.mqtt_client = mock_client

        bridge.cleanup()

        # Verify cleanup was called
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()

    def test_cleanup_can_bus(self):
        """Test CAN bus cleanup."""
        bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="user",
            mqtt_password="pass",
            can_interface="can0",
        )

        # Mock CAN bus
        mock_bus = MagicMock()
        bridge.can_bus = mock_bus

        bridge.cleanup()

        # Verify cleanup was called
        mock_bus.shutdown.assert_called_once()

    def test_cleanup_handles_none(self):
        """Test cleanup handles None gracefully."""
        bridge = MQTTBridge(
            mqtt_host="localhost",
            mqtt_user="user",
            mqtt_password="pass",
            can_interface="can0",
        )

        # Leave mqtt_client and can_bus as None
        bridge.cleanup()  # Should not raise


if __name__ == "__main__":
    unittest.main()
