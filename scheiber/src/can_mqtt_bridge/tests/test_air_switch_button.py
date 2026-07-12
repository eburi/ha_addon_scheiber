"""Tests for the MQTT Air Switch button (Home Assistant event platform) entity."""

import json
from unittest.mock import MagicMock

from can_mqtt_bridge.air_switch_button import MQTTAirSwitchButton

from scheiber.air_switch import AirSwitchButton


def _make_button():
    return AirSwitchButton(
        identity_hex="52ab81",
        button_index=2,
        name="Top Left",
        entity_id="bow_salon_top_left",
    )


def test_publish_discovery_uses_event_platform_shape():
    hardware_button = _make_button()
    client = MagicMock()
    mqtt_button = MQTTAirSwitchButton(
        hardware_button, client, mqtt_topic_prefix="homeassistant"
    )

    mqtt_button.publish_discovery()

    topic, payload = client.publish.call_args[0][:2]
    config = json.loads(payload)

    assert topic == "homeassistant/event/bow_salon_top_left/config"
    assert config["name"] == "Bow Salon Top Left"
    assert config["unique_id"] == "scheiber_air_switch_52ab81_btn2"
    assert config["event_types"] == ["press"]
    assert config["device_class"] == "button"
    assert config["state_topic"] == (
        "homeassistant/scheiber/air_switch/52ab81/btn2/state"
    )
    assert config["availability_topic"] == (
        "homeassistant/scheiber/air_switch/52ab81/btn2/availability"
    )
    assert client.publish.call_args.kwargs.get("retain", True) is True


def test_publish_availability_online_and_offline():
    hardware_button = _make_button()
    client = MagicMock()
    mqtt_button = MQTTAirSwitchButton(hardware_button, client)

    mqtt_button.publish_availability(True)
    assert client.publish.call_args[0][1] == "online"

    mqtt_button.publish_availability(False)
    assert client.publish.call_args[0][1] == "offline"


def test_hardware_press_publishes_event_without_retain():
    hardware_button = _make_button()
    client = MagicMock()
    MQTTAirSwitchButton(hardware_button, client)

    # Simulate a real rising-edge press from the hardware layer.
    hardware_button.handle_observation(True)

    publish_call = next(
        call
        for call in client.publish.call_args_list
        if call[0][0] == "homeassistant/scheiber/air_switch/52ab81/btn2/state"
    )
    payload = json.loads(publish_call[0][1])

    assert payload == {"event_type": "press"}
    assert publish_call.kwargs.get("retain") is False


def test_redundant_press_frames_publish_a_single_event():
    hardware_button = _make_button()
    client = MagicMock()
    MQTTAirSwitchButton(hardware_button, client)

    # Three redundant CAN frames for a single logical press (the real
    # interface always fans this out across three low bytes).
    hardware_button.handle_observation(True)
    hardware_button.handle_observation(True)
    hardware_button.handle_observation(True)

    state_publishes = [
        call
        for call in client.publish.call_args_list
        if call[0][0] == "homeassistant/scheiber/air_switch/52ab81/btn2/state"
    ]
    assert len(state_publishes) == 1


def test_matches_topic_and_handle_command_are_inert():
    hardware_button = _make_button()
    client = MagicMock()
    mqtt_button = MQTTAirSwitchButton(hardware_button, client)

    assert mqtt_button.matches_topic("anything") is False
    mqtt_button.handle_command("PRESS")  # must not raise
    mqtt_button.publish_initial_state()  # must not raise / must not publish
    mqtt_button.subscribe_to_commands()  # must not raise
