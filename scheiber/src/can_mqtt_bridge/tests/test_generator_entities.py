"""
Tests for the generator MQTT entities (switch, buttons, running, phase).
"""

import json
from unittest.mock import MagicMock, Mock, call

import can
import pytest
from can_mqtt_bridge.generator import (
    MQTTGeneratorButton,
    MQTTGeneratorPhase,
    MQTTGeneratorRunning,
    MQTTGeneratorSwitch,
    create_generator_entities,
)

from scheiber.generator import GeneratorControl

AC_STOPPED = can.Message(
    arbitration_id=0x02040B88,
    data=bytes.fromhex("0000000000E60032"),
    is_extended_id=True,
)
ENGINE_RUNNING = can.Message(
    arbitration_id=0x02140B88, data=bytes.fromhex("05"), is_extended_id=True
)
PHASE_STARTING = can.Message(
    arbitration_id=0x02440B88, data=bytes.fromhex("02"), is_extended_id=True
)


def make_control(send=None):
    return GeneratorControl(
        device_id=1,
        name="Generator",
        entity_id="generator",
        send_message_func=send or Mock(),
    )


def published(mock_client, topic):
    """Return payloads published to a topic, in order."""
    return [
        c.args[1]
        for c in mock_client.publish.call_args_list
        if c.args and c.args[0] == topic
    ]


@pytest.fixture
def mqtt_client():
    client = MagicMock()
    client.publish.return_value = MagicMock(rc=0)
    return client


class TestEntitySet:
    def test_create_generator_entities_builds_five(self, mqtt_client):
        entities = create_generator_entities(
            generator=make_control(),
            device_type="source_selector",
            device_id=1,
            mqtt_client=mqtt_client,
            mqtt_topic_prefix="custom",
        )
        assert [type(e) for e in entities] == [
            MQTTGeneratorSwitch,
            MQTTGeneratorButton,
            MQTTGeneratorButton,
            MQTTGeneratorRunning,
            MQTTGeneratorPhase,
        ]
        assert [e.entity_id for e in entities] == [
            "generator",
            "generator_start",
            "generator_stop",
            "generator_running",
            "generator_phase",
        ]
        assert [e.unique_id for e in entities] == [
            "scheiber_source_selector_1_generator",
            "scheiber_source_selector_1_generator_start",
            "scheiber_source_selector_1_generator_stop",
            "scheiber_source_selector_1_generator_running",
            "scheiber_source_selector_1_generator_phase",
        ]
        # Topic prefix is configurable, never hardcoded.
        assert entities[0].command_topic == (
            "custom/scheiber/source_selector/1/generator/set"
        )
        assert entities[0].config_topic == "custom/switch/generator/config"
        assert (
            entities[3].config_topic == "custom/binary_sensor/generator_running/config"
        )


class TestSwitch:
    def make(self, mqtt_client, send=None, read_only=False):
        control = make_control(send)
        entity = MQTTGeneratorSwitch(
            generator=control,
            device_type="source_selector",
            device_id=1,
            mqtt_client=mqtt_client,
            read_only=read_only,
        )
        return control, entity

    def test_discovery_payload(self, mqtt_client):
        _, entity = self.make(mqtt_client)
        entity.publish_discovery()
        topic, payload = mqtt_client.publish.call_args.args[:2]
        config = json.loads(payload)
        assert topic == "homeassistant/switch/generator/config"
        assert config["unique_id"] == "scheiber_source_selector_1_generator"
        assert config["command_topic"] == (
            "homeassistant/scheiber/source_selector/1/generator/set"
        )
        assert config["state_topic"] == (
            "homeassistant/scheiber/source_selector/1/generator/state"
        )
        assert config["optimistic"] is False
        assert config["device"]["identifiers"] == ["scheiber_system"]

    def test_no_state_published_while_unknown(self, mqtt_client):
        _, entity = self.make(mqtt_client)
        entity.publish_initial_state()
        assert published(mqtt_client, entity.state_topic) == []

    def test_state_follows_generator(self, mqtt_client):
        control, entity = self.make(mqtt_client)
        control.process_message(AC_STOPPED)
        assert published(mqtt_client, entity.state_topic) == ["OFF"]
        control.process_message(ENGINE_RUNNING)
        assert published(mqtt_client, entity.state_topic) == ["OFF", "ON"]

    def test_on_command_starts_generator(self, mqtt_client):
        send = Mock()
        control, entity = self.make(mqtt_client, send=send)
        control.process_message(AC_STOPPED)
        entity.handle_command("ON")
        send.assert_called_once_with(0x02460B88, b"\x01")

    def test_off_command_stops_generator(self, mqtt_client):
        send = Mock()
        control, entity = self.make(mqtt_client, send=send)
        control.process_message(ENGINE_RUNNING)
        entity.handle_command("OFF")
        send.assert_called_once_with(0x02460B88, b"\x02")

    def test_interlock_refusal_republishes_real_state(self, mqtt_client):
        send = Mock()
        control, entity = self.make(mqtt_client, send=send)
        control.process_message(ENGINE_RUNNING)
        mqtt_client.publish.reset_mock()
        entity.handle_command("ON")  # already running
        send.assert_not_called()
        assert published(mqtt_client, entity.state_topic) == ["ON"]

    def test_retained_command_is_cleared_and_ignored(self, mqtt_client):
        send = Mock()
        control, entity = self.make(mqtt_client, send=send)
        control.process_message(AC_STOPPED)
        entity.handle_command("ON", is_retained=True, timestamp=0.0)
        send.assert_not_called()
        mqtt_client.publish.assert_any_call(entity.command_topic, None, retain=True)

    def test_read_only_ignores_commands(self, mqtt_client):
        send = Mock()
        control, entity = self.make(mqtt_client, send=send, read_only=True)
        control.process_message(AC_STOPPED)
        entity.handle_command("ON")
        send.assert_not_called()

    def test_matches_only_own_command_topic(self, mqtt_client):
        _, entity = self.make(mqtt_client)
        assert entity.matches_topic(entity.command_topic)
        assert not entity.matches_topic(entity.state_topic)
        assert not entity.matches_topic(
            "homeassistant/scheiber/source_selector/1/generator/start/set"
        )


class TestButtons:
    def test_start_and_stop_buttons(self, mqtt_client):
        send = Mock()
        control = make_control(send)
        control.process_message(AC_STOPPED)
        start = MQTTGeneratorButton(
            "start",
            generator=control,
            device_type="source_selector",
            device_id=1,
            mqtt_client=mqtt_client,
        )
        stop = MQTTGeneratorButton(
            "stop",
            generator=control,
            device_type="source_selector",
            device_id=1,
            mqtt_client=mqtt_client,
        )
        assert start.command_topic == (
            "homeassistant/scheiber/source_selector/1/generator/start/set"
        )
        assert stop.command_topic == (
            "homeassistant/scheiber/source_selector/1/generator/stop/set"
        )
        start.publish_discovery()
        config = json.loads(mqtt_client.publish.call_args.args[1])
        assert config["payload_press"] == "PRESS"
        assert config["unique_id"] == "scheiber_source_selector_1_generator_start"

        start.handle_command("PRESS")
        send.assert_called_once_with(0x02460B88, b"\x01")

        # Stop refused while stopped: no frame, no crash.
        stop.handle_command("PRESS")
        assert send.call_count == 1

        control.process_message(ENGINE_RUNNING)
        stop.handle_command("PRESS")
        assert send.call_args == call(0x02460B88, b"\x02")

    def test_invalid_action_rejected(self, mqtt_client):
        with pytest.raises(ValueError):
            MQTTGeneratorButton(
                "restart",
                generator=make_control(),
                device_type="source_selector",
                device_id=1,
                mqtt_client=mqtt_client,
            )


class TestRunningAndPhase:
    def test_running_binary_sensor(self, mqtt_client):
        control = make_control()
        entity = MQTTGeneratorRunning(
            generator=control,
            device_type="source_selector",
            device_id=1,
            mqtt_client=mqtt_client,
        )
        entity.publish_discovery()
        config = json.loads(mqtt_client.publish.call_args.args[1])
        assert config["device_class"] == "running"
        assert (
            entity.config_topic
            == "homeassistant/binary_sensor/generator_running/config"
        )
        entity.publish_initial_state()
        assert published(mqtt_client, entity.state_topic) == []
        control.process_message(ENGINE_RUNNING)
        assert published(mqtt_client, entity.state_topic) == ["ON"]
        assert not entity.matches_topic(entity.state_topic)

    def test_phase_sensor(self, mqtt_client):
        control = make_control()
        entity = MQTTGeneratorPhase(
            generator=control,
            device_type="source_selector",
            device_id=1,
            mqtt_client=mqtt_client,
        )
        entity.publish_discovery()
        config = json.loads(mqtt_client.publish.call_args.args[1])
        assert config["entity_category"] == "diagnostic"
        control.process_message(PHASE_STARTING)
        assert published(mqtt_client, entity.state_topic) == ["starting"]
