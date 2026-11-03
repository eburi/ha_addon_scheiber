"""
Tests for generator control through a SourceSelector node.

Frames are the ones captured live on 2026-10-26 from node 0x0B88 (bus_id 1)
and in the March 2026 24 h capture. See plan/generator-control.md.
"""

from unittest.mock import Mock

import can
import pytest

from scheiber.can_bus import ScheiberCanBus
from scheiber.generator import GeneratorControl, GeneratorInterlockError
from scheiber.protocol import classify_message_family
from scheiber.source_selector import SourceSelectorDevice
from scheiber.system import ScheiberSystem


def frame(arbitration_id, data_hex):
    return can.Message(
        arbitration_id=arbitration_id,
        data=bytes.fromhex(data_hex),
        is_extended_id=True,
    )


# Node 0x0B88 = bus_id 1, segment 0
CMD_START = frame(0x02460B88, "01")
CMD_STOP = frame(0x02460B88, "02")
START_RELAY_ON = frame(0x02160B88, "0000010100000000")
STOP_RELAY_ON = frame(0x02160B88, "0000000000000101")
RELAYS_OFF = frame(0x02160B88, "0000000000000000")
ENGINE_RUNNING = frame(0x02140B88, "05")
ENGINE_STOPPED = frame(0x02140B88, "04")
ENGINE_START_TRANSIENT = frame(0x02140B88, "14")
PHASE_STARTING = frame(0x02440B88, "02")
PHASE_RUNNING = frame(0x02440B88, "01")
PHASE_STOPPING = frame(0x02440B88, "05")
PHASE_STOPPED = frame(0x02440B88, "00")
AC_STOPPED = frame(0x02040B88, "0000000000E60032")
AC_RAMPING = frame(0x02040B88, "003C003200E10032")
AC_RUNNING = frame(0x02040B88, "00F0003200EB0032")
AC_GLITCH = frame(0x02040B88, "0000041A00E60032")  # 1050 Hz transient after stop
BATTERY_14V4 = frame(0x02060B88, "00900000")
BATTERY_CRANK = frame(0x02060B88, "00680000")
HEARTBEAT = frame(0x00000B88, "080F00FB03")


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


def make_control(**kwargs):
    send = Mock()
    clock = FakeClock()
    control = GeneratorControl(
        device_id=1,
        name="Generator",
        entity_id="generator",
        send_message_func=send,
        time_func=clock,
        **kwargs,
    )
    return control, send, clock


class TestArbitrationIds:
    def test_ids_for_bus_1(self):
        control, _, _ = make_control()
        assert control.command_id == 0x02460B88
        assert control.output_state_id == 0x02160B88
        assert control.engine_state_id == 0x02140B88
        assert control.phase_id == 0x02440B88
        assert control.ac_measurement_id == 0x02040B88
        assert control.dc_measurement_id == 0x02060B88

    def test_ids_for_segmented_address(self):
        control = GeneratorControl(
            device_id=3,
            segment_id=2,
            name="Gen",
            entity_id="gen",
            send_message_func=Mock(),
        )
        # 0x80 | (3 << 3) | 2 = 0x9A
        assert control.command_id == 0x02460B9A
        assert control.ac_measurement_id == 0x02040B9A

    def test_protocol_classifies_new_families(self):
        assert classify_message_family(0x02460B88)["family"] == "command"
        assert classify_message_family(0x02160B88)["family"] == "output_state"
        assert classify_message_family(0x02140B88)["family"] == "engine_state"
        assert classify_message_family(0x02440B88)["family"] == "phase"
        assert classify_message_family(0x02060B88)["family"] == "dc_measurement"


class TestDecoding:
    def test_unknown_before_any_frame(self):
        control, _, _ = make_control()
        assert control.running is None
        assert control.phase_name is None
        assert control.get_state()["running"] is None

    def test_running_derived_from_frequency_before_engine_state(self):
        control, _, _ = make_control()
        control.process_message(AC_STOPPED)
        assert control.running is False
        assert control.voltage_sensor.get_value() == 0.0
        assert control.frequency_sensor.get_value() == 0.0
        assert control.phase_name == "stopped"

        control.process_message(AC_RUNNING)
        assert control.running is True
        assert control.voltage_sensor.get_value() == 240.0
        assert control.frequency_sensor.get_value() == 50.0
        assert control.phase_name == "running"

    def test_engine_state_bit0_is_authoritative(self):
        control, _, _ = make_control()
        control.process_message(AC_RUNNING)
        control.process_message(ENGINE_STOPPED)
        assert control.running is False
        control.process_message(ENGINE_RUNNING)
        assert control.running is True
        control.process_message(ENGINE_START_TRANSIENT)  # 0x14: bit0 clear
        assert control.running is False

    def test_frequency_transient_is_ignored(self):
        control, _, _ = make_control()
        control.process_message(AC_RUNNING)
        control.process_message(AC_GLITCH)
        assert control.frequency_sensor.get_value() == 50.0
        assert control.voltage_sensor.get_value() == 240.0

    def test_battery_voltage_scaled(self):
        control, _, _ = make_control()
        control.process_message(BATTERY_14V4)
        assert control.battery_voltage_sensor.get_value() == 14.4
        control.process_message(BATTERY_CRANK)
        assert control.battery_voltage_sensor.get_value() == 10.4

    def test_phase_names(self):
        control, _, _ = make_control()
        for msg, name in (
            (PHASE_STARTING, "starting"),
            (PHASE_RUNNING, "running"),
            (PHASE_STOPPING, "stopping"),
            (PHASE_STOPPED, "stopped"),
            (frame(0x02440B88, "7F"), "unknown_0x7F"),
        ):
            control.process_message(msg)
            assert control.phase_name == name

    def test_relay_pulses_tracked_from_output_state(self):
        control, _, clock = make_control()
        control.process_message(START_RELAY_ON)
        assert control.start_pulse_active is True
        assert control.stop_pulse_active is False
        control.process_message(RELAYS_OFF)
        assert control.start_pulse_active is False

        control.process_message(STOP_RELAY_ON)
        assert control.stop_pulse_active is True
        control.process_message(RELAYS_OFF)
        assert control.stop_pulse_active is False

    def test_relay_pulse_expires_when_release_frame_missed(self):
        control, _, clock = make_control()
        control.process_message(START_RELAY_ON)
        clock.now += 44
        assert control.start_pulse_active is True
        clock.now += 2
        assert control.start_pulse_active is False

    def test_phase_done_byte_clears_pulses(self):
        control, _, _ = make_control()
        control.process_message(STOP_RELAY_ON)
        control.process_message(PHASE_STOPPED)
        assert control.stop_pulse_active is False

    def test_sensors_exposed(self):
        control, _, _ = make_control()
        ids = [s.entity_id for s in control.get_sensors()]
        assert ids == [
            "generator_voltage",
            "generator_frequency",
            "generator_battery_voltage",
        ]
        units = [s.unit_of_measurement for s in control.get_sensors()]
        assert units == ["V", "Hz", "V"]

    def test_observers_notified_on_change_only(self):
        control, _, _ = make_control()
        observer = Mock()
        control.subscribe(observer)
        control.process_message(AC_STOPPED)
        control.process_message(AC_STOPPED)
        control.process_message(BATTERY_14V4)
        assert observer.call_count == 1
        assert observer.call_args[0][0]["running"] is False
        control.process_message(ENGINE_RUNNING)
        assert observer.call_count == 2
        assert observer.call_args[0][0]["running"] is True


class TestCommandsAndInterlock:
    def test_start_sends_command_frame(self):
        control, send, _ = make_control()
        control.process_message(AC_STOPPED)
        control.start()
        send.assert_called_once_with(0x02460B88, bytes([0x01]))

    def test_stop_sends_command_frame(self):
        control, send, _ = make_control()
        control.process_message(ENGINE_RUNNING)
        control.stop()
        send.assert_called_once_with(0x02460B88, bytes([0x02]))

    def test_set_maps_to_start_and_stop(self):
        control, send, _ = make_control()
        control.process_message(AC_STOPPED)
        control.set(True)
        control.process_message(ENGINE_RUNNING)
        control.set(False)
        assert [c.args for c in send.call_args_list] == [
            (0x02460B88, b"\x01"),
            (0x02460B88, b"\x02"),
        ]

    def test_refuses_while_state_unknown(self):
        control, send, _ = make_control()
        with pytest.raises(GeneratorInterlockError, match="state unknown"):
            control.start()
        with pytest.raises(GeneratorInterlockError, match="state unknown"):
            control.stop()
        send.assert_not_called()

    def test_refuses_start_when_already_running(self):
        control, send, _ = make_control()
        control.process_message(ENGINE_RUNNING)
        with pytest.raises(GeneratorInterlockError, match="already running"):
            control.start()
        send.assert_not_called()

    def test_refuses_stop_when_already_stopped(self):
        control, send, _ = make_control()
        control.process_message(AC_STOPPED)
        with pytest.raises(GeneratorInterlockError, match="already stopped"):
            control.stop()
        send.assert_not_called()

    def test_refuses_while_start_pulse_active(self):
        control, send, _ = make_control()
        control.process_message(AC_STOPPED)
        control.process_message(START_RELAY_ON)
        with pytest.raises(GeneratorInterlockError, match="start relay"):
            control.stop()
        with pytest.raises(GeneratorInterlockError, match="start relay"):
            control.start()
        send.assert_not_called()

    def test_refuses_while_stop_pulse_active(self):
        control, send, _ = make_control()
        control.process_message(ENGINE_STOPPED)
        control.process_message(STOP_RELAY_ON)
        with pytest.raises(GeneratorInterlockError, match="stop relay"):
            control.start()
        send.assert_not_called()

    def test_full_cycle_from_live_capture(self):
        """Replays the 2026-10-26 cycle 1 sequence end to end."""
        control, send, clock = make_control()
        control.process_message(AC_STOPPED)
        control.process_message(ENGINE_STOPPED)
        control.start()
        send.assert_called_once()
        control.process_message(CMD_START)
        control.process_message(START_RELAY_ON)
        control.process_message(PHASE_STARTING)
        assert control.phase_name == "starting"
        assert control.start_pulse_active
        control.process_message(ENGINE_START_TRANSIENT)
        control.process_message(ENGINE_STOPPED)
        control.process_message(ENGINE_RUNNING)
        control.process_message(AC_RAMPING)
        control.process_message(AC_RUNNING)
        assert control.running is True
        clock.now += 29.93
        control.process_message(RELAYS_OFF)
        control.process_message(PHASE_RUNNING)
        assert not control.start_pulse_active
        assert control.phase_name == "running"

        control.stop()
        assert send.call_count == 2
        control.process_message(STOP_RELAY_ON)
        control.process_message(PHASE_STOPPING)
        control.process_message(ENGINE_STOPPED)
        control.process_message(AC_STOPPED)
        assert control.running is False
        assert control.stop_pulse_active
        with pytest.raises(GeneratorInterlockError):
            control.start()
        clock.now += 59.86
        control.process_message(RELAYS_OFF)
        control.process_message(PHASE_STOPPED)
        assert not control.stop_pulse_active
        assert control.phase_name == "stopped"


class TestReadOnlyBus:
    def test_read_only_bus_blocks_generator_command(self):
        bus = ScheiberCanBus(interface="vcan0", read_only=True)
        bus.bus = Mock()
        control = GeneratorControl(
            device_id=1,
            name="Generator",
            entity_id="generator",
            send_message_func=bus.send_message,
        )
        control.process_message(AC_STOPPED)
        control.start()
        bus.bus.send.assert_not_called()


class TestSourceSelectorIntegration:
    def make_device(self, can_bus=None, with_generator=True):
        config = {
            "sensors": [
                {
                    "sensor_type": "voltage",
                    "name": "Shore voltage",
                    "entity_id": "shore_voltage",
                    "matcher": {"pattern": 0x02040B88, "mask": 0xFFFFFFFF},
                    "value_config": {
                        "start_byte": 4,
                        "bit_length": 16,
                        "endian": "big",
                        "scale": 1.0,
                    },
                }
            ]
        }
        if with_generator:
            config["generator"] = {"name": "Generator", "entity_id": "generator"}
        return SourceSelectorDevice(
            device_id=1, can_bus=can_bus or Mock(), config=config
        )

    def test_without_generator_section_stays_read_only(self):
        device = self.make_device(with_generator=False)
        assert device.get_generators() == []
        assert device.generator is None
        assert [s.entity_id for s in device.get_sensors()] == ["shore_voltage"]

    def test_generator_section_adds_control_and_sensors(self):
        device = self.make_device()
        assert len(device.get_generators()) == 1
        assert device.generator.entity_id == "generator"
        assert [s.entity_id for s in device.get_sensors()] == [
            "shore_voltage",
            "generator_voltage",
            "generator_frequency",
            "generator_battery_voltage",
        ]
        patterns = {m.pattern for m in device.get_matchers()}
        assert {0x02460B88, 0x02160B88, 0x02140B88, 0x02440B88, 0x02060B88} <= patterns

    def test_commands_go_through_bus_wrapper(self):
        can_bus = Mock()
        device = self.make_device(can_bus=can_bus)
        device.process_message(AC_STOPPED)
        device.generator.start()
        can_bus.send_message.assert_called_once_with(0x02460B88, b"\x01")

    def test_system_routes_frames_to_generator(self):
        device = self.make_device()
        system = ScheiberSystem(devices=[device], can_bus=Mock())
        system._on_can_message(AC_RUNNING)
        system._on_can_message(ENGINE_RUNNING)
        system._on_can_message(BATTERY_14V4)
        assert device.generator.running is True
        assert device.generator.battery_voltage_sensor.get_value() == 14.4
        # Configured free-form sensor still decoded from the same frame.
        assert device.get_sensors()[0].get_value() == 235.0
        # Node frames are known, not logged as unknown IDs.
        assert 0x02140B88 not in system._unknown_ids

    def test_state_persistence_includes_generator_sensors(self):
        device = self.make_device()
        device.process_message(AC_RUNNING)
        device.process_message(BATTERY_14V4)
        state = device.store_to_state()
        assert state["generator_frequency"] == 50.0
        assert state["generator_battery_voltage"] == 14.4

        restored = self.make_device()
        restored.restore_from_state(state)
        assert restored.generator.frequency_sensor.get_value() == 50.0
