"""
Test cases for MQTTBridge class.

Tests initialization, MQTT discovery, state publishing, and command handling.
"""

import json
import time
import pytest
from unittest.mock import MagicMock, Mock, patch, call
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from can_mqtt_bridge.bridge import MQTTBridge


def create_mock_mqtt_message(topic: str, payload: bytes, retained: bool = False):
    """Helper to create a mock MQTT message with all required attributes."""
    msg = MagicMock()
    msg.topic = topic
    msg.payload = payload
    msg.retain = retained
    msg.timestamp = time.time() if retained else None
    return msg


class TestMQTTBridgeInit:
    """Test MQTTBridge initialization."""

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_initialization_minimal(self, mock_create_system, mock_mqtt_client):
        """Test bridge initializes with minimal parameters."""
        mock_system = MagicMock()
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(
            can_interface="can0",
            mqtt_host="localhost",
        )

        assert bridge.mqtt_topic_prefix == "homeassistant"
        assert bridge.read_only is False
        assert bridge._running is False

        # Verify system creation
        mock_create_system.assert_called_once_with(
            can_interface="can0",
            config_path=None,
            state_file=None,
            log_level="info",
            read_only=False,
        )

        # Verify MQTT connection
        mock_client.connect.assert_called_once_with("localhost", 1883, 60)
        mock_client.loop_start.assert_called_once()

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_initialization_full_params(self, mock_create_system, mock_mqtt_client):
        """Test bridge initializes with all parameters."""
        mock_system = MagicMock()
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(
            can_interface="can1",
            mqtt_host="mqtt.example.com",
            mqtt_port=8883,
            mqtt_user="test_user",
            mqtt_password="test_pass",
            mqtt_topic_prefix="boat",
            config_path="/path/to/config.yaml",
            state_file="/path/to/state.json",
            log_level="debug",
            read_only=True,
        )

        assert bridge.mqtt_topic_prefix == "boat"
        assert bridge.read_only is True

        # Verify credentials
        mock_client.username_pw_set.assert_called_once_with("test_user", "test_pass")

        # Verify MQTT connection
        mock_client.connect.assert_called_once_with("mqtt.example.com", 8883, 60)

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_initialization_mqtt_failure(self, mock_create_system, mock_mqtt_client):
        """Test bridge handles MQTT connection failure."""
        mock_system = MagicMock()
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_client.connect.side_effect = Exception("Connection failed")
        mock_mqtt_client.return_value = mock_client

        with pytest.raises(Exception, match="Connection failed"):
            MQTTBridge(can_interface="can0", mqtt_host="localhost")


class TestMQTTBridgeStartStop:
    """Test bridge start/stop lifecycle."""

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_start_bridge(self, mock_create_system, mock_mqtt_client):
        """Test starting the bridge."""
        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = []
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        assert bridge._running is True
        mock_system.start.assert_called_once()

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_start_already_running(self, mock_create_system, mock_mqtt_client):
        """Test starting bridge when already running does nothing."""
        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = []
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()
        mock_system.start.reset_mock()

        bridge.start()  # Second call

        mock_system.start.assert_not_called()

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_stop_bridge(self, mock_create_system, mock_mqtt_client):
        """Test stopping the bridge."""
        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = []
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()
        bridge.stop()

        assert bridge._running is False
        mock_system.stop.assert_called_once()
        mock_client.loop_stop.assert_called_once()
        mock_client.disconnect.assert_called_once()


class TestMQTTDiscoveryLights:
    """Test MQTT discovery config publishing for lights."""

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_light_discovery_config(self, mock_create_system, mock_mqtt_client):
        """Test light discovery config is published correctly."""
        # Setup mock light
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": False, "brightness": 0}
        mock_light.subscribe = Mock()

        # Setup mock device
        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        # Find discovery config publish call
        discovery_calls = [
            call
            for call in mock_client.publish.call_args_list
            if "/config" in str(call)
        ]

        assert len(discovery_calls) > 0

        # Get the discovery config
        config_topic = discovery_calls[0][0][0]
        config_payload = discovery_calls[0][0][1]
        config = json.loads(config_payload)

        # Verify config topic (uses entity_id)
        assert config_topic == "homeassistant/light/s1/config"

        # Verify config content
        assert config["name"] == "S1"
        assert config["unique_id"] == "scheiber_bloc9_7_s1"
        assert config["state_topic"] == "homeassistant/scheiber/bloc9/7/s1/state"
        assert config["command_topic"] == "homeassistant/scheiber/bloc9/7/s1/set"
        assert (
            config["availability_topic"]
            == "homeassistant/scheiber/bloc9/7/s1/availability"
        )
        assert config["brightness"] is True
        assert config["brightness_scale"] == 255
        assert config["schema"] == "json"
        assert config["optimistic"] is False

        # Verify unified device structure
        assert config["device"]["identifiers"] == ["scheiber_system"]
        assert config["device"]["name"] == "Scheiber"
        assert config["device"]["manufacturer"] == "Scheiber"
        assert config["device"]["model"] == "Marine Lighting Control System"

        # Verify color mode support
        assert config["supported_color_modes"] == ["brightness"]

        # Verify effect support with all easing functions
        assert config["effect"] is True
        assert "effect_list" in config
        assert isinstance(config["effect_list"], list)
        assert len(config["effect_list"]) == 13
        # Verify key easing functions are present
        assert "linear" in config["effect_list"]
        assert "ease_in_out_sine" in config["effect_list"]
        assert "ease_in_quad" in config["effect_list"]
        assert "ease_out_quart" in config["effect_list"]

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_light_availability_published(self, mock_create_system, mock_mqtt_client):
        """Test light availability is published as online."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": False, "brightness": 0}
        mock_light.subscribe = Mock()

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        # Find availability publish call
        availability_calls = [
            call
            for call in mock_client.publish.call_args_list
            if "availability" in str(call[0][0]) and call[0][1] == "online"
        ]

        assert len(availability_calls) > 0
        assert (
            availability_calls[0][0][0]
            == "homeassistant/scheiber/bloc9/7/s1/availability"
        )

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_light_command_subscription(self, mock_create_system, mock_mqtt_client):
        """Test bridge subscribes to light command topics."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": False, "brightness": 0}
        mock_light.subscribe = Mock()

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        # Verify subscription
        subscribe_calls = [call[0][0] for call in mock_client.subscribe.call_args_list]
        assert "homeassistant/scheiber/bloc9/7/s1/set" in subscribe_calls


class TestMQTTDiscoverySwitches:
    """Test MQTT discovery config publishing for switches."""

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_switch_discovery_config(self, mock_create_system, mock_mqtt_client):
        """Test switch discovery config is published correctly."""
        mock_switch = MagicMock()
        mock_switch.name = "Switch 1"
        mock_switch.entity_id = "switch_1"
        mock_switch.switch_nr = 0
        mock_switch.get_state.return_value = False
        mock_switch.subscribe = Mock()

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = []
        mock_device.get_switches.return_value = [mock_switch]

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        # Find discovery config
        discovery_calls = [
            call
            for call in mock_client.publish.call_args_list
            if "/config" in str(call)
        ]

        config_topic = discovery_calls[0][0][0]
        config_payload = discovery_calls[0][0][1]
        config = json.loads(config_payload)

        # Verify config (uses entity_id in config topic, s1 in state topic)
        assert config_topic == "homeassistant/switch/switch_1/config"
        assert config["name"] == "Switch 1"
        assert config["unique_id"] == "scheiber_bloc9_7_s1"
        assert config["state_topic"] == "homeassistant/scheiber/bloc9/7/s1/state"
        assert config["command_topic"] == "homeassistant/scheiber/bloc9/7/s1/set"
        assert (
            config["availability_topic"]
            == "homeassistant/scheiber/bloc9/7/s1/availability"
        )
        assert config["payload_on"] == "ON"
        assert config["payload_off"] == "OFF"
        assert config["state_on"] == "ON"
        assert config["state_off"] == "OFF"
        assert config["optimistic"] is False


class TestStatePublishing:
    """Test state publishing to MQTT."""

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_light_state_change_published(self, mock_create_system, mock_mqtt_client):
        """Test light state changes are published to MQTT."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": False, "brightness": 0}

        # Capture the callback
        callback_holder = []

        def capture_callback(callback):
            callback_holder.append(callback)

        mock_light.subscribe = capture_callback

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        # Reset publish calls
        mock_client.publish.reset_mock()

        # Trigger state change
        assert len(callback_holder) == 1
        state_callback = callback_holder[0]
        state_callback({"state": True, "brightness": 200})

        # Verify state published
        publish_calls = [call[0] for call in mock_client.publish.call_args_list]
        state_publishes = [call for call in publish_calls if call[0].endswith("/state")]

        assert len(state_publishes) == 1
        topic, payload = state_publishes[0]
        assert topic == "homeassistant/scheiber/bloc9/7/s1/state"

        state = json.loads(payload)
        assert state["state"] == "ON"
        assert state["brightness"] == 200

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_switch_state_change_published(self, mock_create_system, mock_mqtt_client):
        """Test switch state changes are published to MQTT."""
        mock_switch = MagicMock()
        mock_switch.name = "Switch 1"
        mock_switch.entity_id = "switch_1"
        mock_switch.switch_nr = 0
        mock_switch.get_state.return_value = False

        callback_holder = []

        def capture_callback(callback):
            callback_holder.append(callback)

        mock_switch.subscribe = capture_callback

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = []
        mock_device.get_switches.return_value = [mock_switch]

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        mock_client.publish.reset_mock()

        # Trigger state change
        state_callback = callback_holder[0]
        state_callback({"state": True})

        # Verify
        publish_calls = [call[0] for call in mock_client.publish.call_args_list]
        state_publishes = [call for call in publish_calls if call[0].endswith("/state")]

        assert len(state_publishes) == 1
        topic, payload = state_publishes[0]
        assert payload == "ON"


class TestCommandHandling:
    """Test MQTT command handling."""

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_light_brightness_command(self, mock_create_system, mock_mqtt_client):
        """Test handling brightness command for light."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": False, "brightness": 0}
        mock_light.subscribe = Mock()
        mock_light.set = Mock()
        mock_light._default_easing = "ease_in_out_sine"

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        # Verify entities were created
        assert len(bridge._mqtt_entities) > 0

        # Simulate MQTT message
        msg = create_mock_mqtt_message(
            "homeassistant/scheiber/bloc9/7/s1/set", b'{"brightness": 150}'
        )

        bridge._on_mqtt_message(None, None, msg)

        # Verify command sent to light
        mock_light.set.assert_called_once_with(state=True, brightness=150, effect=None)

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_light_on_command(self, mock_create_system, mock_mqtt_client):
        """Test handling ON command for light."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": False, "brightness": 0}
        mock_light.subscribe = Mock()
        mock_light.set_brightness = Mock()

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        msg = create_mock_mqtt_message(
            "homeassistant/scheiber/bloc9/7/s1/set", b'{"state": "ON"}'
        )

        bridge._on_mqtt_message(None, None, msg)

        mock_light.set_brightness.assert_called_once_with(255)

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_fade_command_with_effect(self, mock_create_system, mock_mqtt_client):
        """Test fade command with custom easing effect."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": True, "brightness": 128}
        mock_light.subscribe = Mock()

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        # Simulate fade command with custom effect
        command_payload = json.dumps(
            {
                "state": "ON",
                "brightness": 200,
                "transition": 2.5,
                "effect": "ease_in_quad",
            }
        )

        # Find the message callback and invoke it
        on_message = mock_client.on_message
        msg = create_mock_mqtt_message(
            "homeassistant/scheiber/bloc9/7/s1/set", command_payload.encode()
        )
        on_message(mock_client, None, msg)

        # Verify fade_to was called with correct easing
        mock_light.fade_to.assert_called_once_with(
            200, duration=2.5, easing="ease_in_quad"
        )

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_fade_command_default_easing(self, mock_create_system, mock_mqtt_client):
        """Test fade command defaults to ease_in_out_sine when no effect specified."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": True, "brightness": 128}
        mock_light.subscribe = Mock()
        mock_light._default_easing = "ease_in_out_sine"

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        # Simulate fade command without effect
        command_payload = json.dumps(
            {"state": "ON", "brightness": 200, "transition": 2.5}
        )

        # Find the message callback and invoke it
        on_message = mock_client.on_message
        msg = create_mock_mqtt_message(
            "homeassistant/scheiber/bloc9/7/s1/set", command_payload.encode()
        )
        on_message(mock_client, None, msg)

        # Verify fade_to was called with default easing
        mock_light.fade_to.assert_called_once_with(
            200, duration=2.5, easing="ease_in_out_sine"
        )

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_fade_command(self, mock_create_system, mock_mqtt_client):
        """Test handling fade transition command."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": False, "brightness": 0}
        mock_light.subscribe = Mock()
        mock_light.fade_to = Mock()
        mock_light._default_easing = "ease_in_out_sine"

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        msg = create_mock_mqtt_message(
            "homeassistant/scheiber/bloc9/7/s1/set",
            b'{"brightness": 200, "transition": 2}',
        )

        bridge._on_mqtt_message(None, None, msg)

        mock_light.fade_to.assert_called_once_with(
            200, duration=2, easing="ease_in_out_sine"
        )

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_multiple_easing_effects(self, mock_create_system, mock_mqtt_client):
        """Test that different easing effects are properly passed to hardware layer."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": True, "brightness": 128}
        mock_light.subscribe = Mock()

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        # Test various easing functions
        test_cases = [
            ("linear", 180, 1.0),
            ("ease_in_sine", 200, 2.0),
            ("ease_out_sine", 150, 1.5),
            ("ease_in_out_sine", 255, 3.0),
            ("ease_in_quad", 100, 0.5),
            ("ease_out_quad", 220, 2.5),
            ("ease_in_out_quad", 80, 1.2),
            ("ease_in_cubic", 190, 1.8),
            ("ease_out_cubic", 160, 2.2),
            ("ease_in_out_cubic", 240, 3.5),
            ("ease_in_quart", 120, 1.1),
            ("ease_out_quart", 210, 2.8),
            ("ease_in_out_quart", 170, 2.3),
        ]

        on_message = mock_client.on_message

        for easing, brightness, duration in test_cases:
            mock_light.fade_to.reset_mock()

            command_payload = json.dumps(
                {
                    "state": "ON",
                    "brightness": brightness,
                    "transition": duration,
                    "effect": easing,
                }
            )

            msg = create_mock_mqtt_message(
                "homeassistant/scheiber/bloc9/7/s1/set", command_payload.encode()
            )
            on_message(mock_client, None, msg)

            # Verify correct easing was passed to hardware
            mock_light.fade_to.assert_called_once_with(
                brightness, duration=duration, easing=easing
            )

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_light_flash_command(self, mock_create_system, mock_mqtt_client):
        """Test handling flash effect command."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": False, "brightness": 0}
        mock_light.subscribe = Mock()
        mock_light.flash = Mock()

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        msg = create_mock_mqtt_message(
            "homeassistant/scheiber/bloc9/7/s1/set", b'{"flash": "short"}'
        )

        bridge._on_mqtt_message(None, None, msg)

        mock_light.flash.assert_called_once_with(count=3)

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_switch_on_command(self, mock_create_system, mock_mqtt_client):
        """Test handling ON command for switch."""
        mock_switch = MagicMock()
        mock_switch.name = "Switch 1"
        mock_switch.entity_id = "switch_1"
        mock_switch.switch_nr = 0
        mock_switch.get_state.return_value = False
        mock_switch.subscribe = Mock()
        mock_switch.set = Mock()

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = []
        mock_device.get_switches.return_value = [mock_switch]

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost")
        bridge.start()

        msg = create_mock_mqtt_message("homeassistant/scheiber/bloc9/7/s1/set", b"ON")

        bridge._on_mqtt_message(None, None, msg)

        mock_switch.set.assert_called_once_with(True)

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_read_only_mode_ignores_commands(
        self, mock_create_system, mock_mqtt_client
    ):
        """Test read-only mode ignores all commands."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": False, "brightness": 0}
        mock_light.subscribe = Mock()

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(can_interface="can0", mqtt_host="localhost", read_only=True)
        bridge.start()

        msg = create_mock_mqtt_message(
            "homeassistant/scheiber/bloc9/7/s1/set", b'{"brightness": 150}'
        )

        bridge._on_mqtt_message(None, None, msg)

        # Verify no command sent
        mock_light.set_brightness.assert_not_called()


class TestTopicPrefix:
    """Test custom MQTT topic prefix."""

    @patch("can_mqtt_bridge.bridge.mqtt.Client")
    @patch("can_mqtt_bridge.bridge.create_scheiber_system")
    def test_custom_topic_prefix(self, mock_create_system, mock_mqtt_client):
        """Test using custom topic prefix."""
        mock_light = MagicMock()
        mock_light.name = "S1"  # Human-readable name
        mock_light.entity_id = "s1"  # Entity ID
        mock_light.switch_nr = 0  # 0-based index
        mock_light.get_state.return_value = {"state": False, "brightness": 0}
        mock_light.subscribe = Mock()

        mock_device = MagicMock()
        mock_device.__class__.__name__ = "Bloc9Device"
        mock_device.device_id = 7
        mock_device.get_lights.return_value = [mock_light]
        mock_device.get_switches.return_value = []

        mock_system = MagicMock()
        mock_system.get_all_devices.return_value = [mock_device]
        mock_create_system.return_value = mock_system

        mock_client = MagicMock()
        mock_mqtt_client.return_value = mock_client

        bridge = MQTTBridge(
            can_interface="can0", mqtt_host="localhost", mqtt_topic_prefix="boat"
        )
        bridge.start()

        # Find discovery config
        discovery_calls = [
            call
            for call in mock_client.publish.call_args_list
            if "/config" in str(call)
        ]

        config_topic = discovery_calls[0][0][0]
        config_payload = discovery_calls[0][0][1]
        config = json.loads(config_payload)

        # Verify custom prefix used (config topic uses entity_id)
        assert config_topic == "boat/light/s1/config"
        assert config["state_topic"] == "boat/scheiber/bloc9/7/s1/state"
        assert config["command_topic"] == "boat/scheiber/bloc9/7/s1/set"
        assert config["availability_topic"] == "boat/scheiber/bloc9/7/s1/availability"
