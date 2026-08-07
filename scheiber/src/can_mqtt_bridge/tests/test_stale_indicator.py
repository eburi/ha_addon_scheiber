"""
Tests for the system-wide stale-output aggregate and its MQTT binary sensor.
"""

import json
from unittest.mock import Mock

import can
from can_mqtt_bridge.stale_indicator import MQTTStaleIndicator

from scheiber.bloc9 import Bloc9Device
from scheiber.output import Output
from scheiber.system import ScheiberSystem

# Real stuck frame from Bloc9 4_3 S1 on Buttercup: brightness 242 while
# de-energised (mode 0x10, state 0x00).
PHANTOM_S1 = can.Message(
    arbitration_id=0x021606A3,
    data=bytes.fromhex("F200100000000000"),
    is_extended_id=True,
)
HEARTBEAT = can.Message(
    arbitration_id=0x000006A3,
    data=bytes.fromhex("0810052CCA"),
    is_extended_id=True,
)


def _make_system():
    device = Bloc9Device(
        device_id=4,
        segment_id=3,
        can_bus=Mock(),
        lights_config={"s1": {"name": "Bathroom", "entity_id": "bathroom"}},
    )
    system = ScheiberSystem(devices=[device], can_bus=Mock())
    return system, device


class TestSystemStaleAggregate:
    def test_clean_system_reports_no_stale_outputs(self):
        system, _ = _make_system()

        assert system.has_stale_outputs() is False
        assert system.get_stale_outputs() == []

    def test_aggregates_stale_outputs_across_devices(self):
        system, _ = _make_system()

        for _ in range(Output.STALE_MIN_OBSERVATIONS):
            system._on_can_message(PHANTOM_S1)

        assert system.has_stale_outputs() is True
        assert system.get_stale_outputs() == ["bathroom"]

    def test_devices_without_stale_support_are_ignored(self):
        """Non-Bloc9 devices have no get_stale_outputs and must not break the scan."""
        device = Mock(spec=["device_type", "device_id", "segment_id", "get_matchers"])
        device.device_type = "bloc7"
        device.device_id = 1
        device.segment_id = 0
        device.get_matchers.return_value = []

        system = ScheiberSystem(devices=[device], can_bus=Mock())

        assert system.get_stale_outputs() == []

    def test_observer_fires_on_transition_only(self):
        system, _ = _make_system()
        seen = []
        system.subscribe_to_stale_change(seen.append)

        # Subscribing primes the observer with the current value.
        assert seen == [False]

        for _ in range(Output.STALE_MIN_OBSERVATIONS * 3):
            system._on_can_message(PHANTOM_S1)

        # Exactly one further notification despite many stale frames.
        assert seen == [False, True]

    def test_observer_fires_on_recovery(self):
        system, device = _make_system()
        seen = []
        system.subscribe_to_stale_change(seen.append)

        for _ in range(Output.STALE_MIN_OBSERVATIONS):
            system._on_can_message(PHANTOM_S1)
        assert seen[-1] is True

        # A recovered Bloc9 goes silent; the heartbeat expires the report.
        device.lights[0]._stale_last_seen = -Output.STALE_RECOVERY_SECONDS * 2
        system._on_can_message(HEARTBEAT)

        assert seen[-1] is False
        assert system.has_stale_outputs() is False

    def test_failing_observer_does_not_break_processing(self):
        system, _ = _make_system()

        def boom(_):
            raise RuntimeError("observer failed")

        system.subscribe_to_stale_change(boom)
        for _ in range(Output.STALE_MIN_OBSERVATIONS):
            system._on_can_message(PHANTOM_S1)

        assert system.has_stale_outputs() is True


class TestStaleIndicatorEntity:
    def _make(self):
        system, device = _make_system()
        client = Mock()
        indicator = MQTTStaleIndicator(system=system, mqtt_client=client)
        return system, device, client, indicator

    def test_discovery_config_is_a_problem_binary_sensor(self):
        _, _, client, indicator = self._make()

        indicator.publish_discovery()

        topic, payload = client.publish.call_args[0][:2]
        assert topic == "homeassistant/binary_sensor/scheiber_stale_outputs/config"
        config = json.loads(payload)
        assert config["device_class"] == "problem"
        assert config["entity_category"] == "diagnostic"
        assert config["payload_on"] == "ON"
        assert config["unique_id"] == "scheiber_scheiber_stale_outputs"
        # Must attach to the existing single Scheiber device.
        assert config["device"]["identifiers"] == ["scheiber_system"]

    def test_publishes_on_when_output_goes_stale(self):
        system, _, client, indicator = self._make()
        client.reset_mock()

        for _ in range(Output.STALE_MIN_OBSERVATIONS):
            system._on_can_message(PHANTOM_S1)

        states = [
            c[0][1]
            for c in client.publish.call_args_list
            if c[0][0] == "homeassistant/scheiber/system/stale_outputs/state"
        ]
        assert states == ["ON"]

    def test_publishes_off_on_recovery(self):
        system, device, client, indicator = self._make()

        for _ in range(Output.STALE_MIN_OBSERVATIONS):
            system._on_can_message(PHANTOM_S1)
        client.reset_mock()

        device.lights[0]._stale_last_seen = -Output.STALE_RECOVERY_SECONDS * 2
        system._on_can_message(HEARTBEAT)

        states = [
            c[0][1]
            for c in client.publish.call_args_list
            if c[0][0] == "homeassistant/scheiber/system/stale_outputs/state"
        ]
        assert states == ["OFF"]

    def test_state_is_retained(self):
        system, _, client, indicator = self._make()
        client.reset_mock()

        indicator.publish_state()

        call = client.publish.call_args
        assert call[0][0] == "homeassistant/scheiber/system/stale_outputs/state"
        assert call[1]["retain"] is True

    def test_respects_topic_prefix(self):
        system, _ = _make_system()
        client = Mock()

        indicator = MQTTStaleIndicator(
            system=system, mqtt_client=client, mqtt_topic_prefix="boat"
        )

        assert indicator.config_topic.startswith("boat/binary_sensor/")
        assert indicator.state_topic.startswith("boat/scheiber/system/")
