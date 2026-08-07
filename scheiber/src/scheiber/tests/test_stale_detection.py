"""
Tests for stale-setpoint detection on Bloc9 outputs.

A Bloc9 stuck in a hold-to-dim cycle keeps broadcasting a brightness setpoint
while the output is de-energised, so the lamp stays dark. All frames here are
taken from a real capture of Bloc9 4_3 on Buttercup (firmware 08.16.05), whose
S1 and S3 were stuck for weeks.
"""

import can

from scheiber.bloc9 import Bloc9Device
from scheiber.output import Output

try:
    from unittest.mock import Mock
except ImportError:  # pragma: no cover
    from mock import Mock


def _msg(arbitration_id: int, data: bytes) -> can.Message:
    return can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=True)


# Real frames from Bloc9 4_3 (bus 4, segment 3, address byte 0xA3).
# S1 phantom: brightness 242, mode 0x10 (PWM selected, not energised), state 0x00.
PHANTOM_S1 = _msg(0x021606A3, bytes.fromhex("F200100000000000"))
# The other half of the stuck cycle: a clean off frame.
CLEAN_OFF_S1 = _msg(0x021606A3, bytes.fromhex("0000000000000000"))
# S1 genuinely on via PWM during a ramp (mode bit set, state bit still lagging).
RAMPING_S1 = _msg(0x021606A3, bytes.fromhex("8000110000000000"))


def _make_light():
    device = Bloc9Device(
        device_id=4,
        segment_id=3,
        can_bus=Mock(),
        lights_config={"s1": {"name": "Bathroom", "entity_id": "bathroom"}},
    )
    return device, device.lights[0]


class TestStaleDetection:
    def test_single_phantom_frame_does_not_report_stale(self):
        """One odd frame must not trip the detector."""
        _, light = _make_light()

        light.process_matching_message(PHANTOM_S1)

        assert light.is_stale() is False

    def test_repeated_phantom_frames_report_stale(self):
        """Sustained phantom setpoints are reported."""
        _, light = _make_light()

        for _ in range(Output.STALE_MIN_OBSERVATIONS):
            light.process_matching_message(PHANTOM_S1)

        assert light.is_stale() is True
        # The entity must still read OFF: the lamp really is dark.
        assert light.get_state() == {"state": False, "brightness": 0}

    def test_stuck_cycle_alternating_frames_reports_stale(self):
        """The real cycle alternates phantom and clean-off frames.

        The clean-off half must not reset the detector, or a stuck output would
        never be reported.
        """
        _, light = _make_light()

        for _ in range(Output.STALE_MIN_OBSERVATIONS):
            light.process_matching_message(CLEAN_OFF_S1)
            light.process_matching_message(PHANTOM_S1)

        assert light.is_stale() is True

    def test_normal_operation_never_reports_stale(self):
        """Ramping and switching off must not trip the detector."""
        _, light = _make_light()

        for _ in range(20):
            light.process_matching_message(RAMPING_S1)
            light.process_matching_message(CLEAN_OFF_S1)

        assert light.is_stale() is False

    def test_observations_outside_window_do_not_accumulate(self):
        """Phantom frames spread beyond the window must not add up."""
        _, light = _make_light()
        frame = Output.decode_output_frame(PHANTOM_S1, 0)

        # One observation every window-length: never enough within any window.
        for i in range(10):
            light._note_stale_sample(frame, now=i * Output.STALE_WINDOW_SECONDS)

        assert light.is_stale() is False


class TestStaleRecovery:
    def test_recovers_after_quiet_period(self):
        """Sustained silence clears the report."""
        _, light = _make_light()
        frame = Output.decode_output_frame(PHANTOM_S1, 0)

        for i in range(Output.STALE_MIN_OBSERVATIONS):
            light._note_stale_sample(frame, now=float(i))
        assert light.is_stale() is True

        light.check_stale_recovery(now=Output.STALE_RECOVERY_SECONDS + 10)

        assert light.is_stale() is False

    def test_does_not_recover_too_early(self):
        """Recovery must wait out the full quiet period."""
        _, light = _make_light()
        frame = Output.decode_output_frame(PHANTOM_S1, 0)

        for i in range(Output.STALE_MIN_OBSERVATIONS):
            light._note_stale_sample(frame, now=float(i))

        light.check_stale_recovery(now=Output.STALE_RECOVERY_SECONDS - 1)

        assert light.is_stale() is True

    def test_heartbeat_drives_recovery(self):
        """A recovered Bloc9 goes silent, so the heartbeat must expire the report."""
        device, light = _make_light()
        frame = Output.decode_output_frame(PHANTOM_S1, 0)

        for i in range(Output.STALE_MIN_OBSERVATIONS):
            light._note_stale_sample(frame, now=float(i))
        assert light.is_stale() is True

        # Rewind last-seen so the quiet period has elapsed, then heartbeat.
        light._stale_last_seen = -Output.STALE_RECOVERY_SECONDS * 2
        device.process_message(_msg(0x000006A3, bytes.fromhex("0810052CCA")))

        assert light.is_stale() is False

    def test_device_lists_stale_outputs(self):
        """The device exposes which outputs are currently stale."""
        device, light = _make_light()

        assert device.get_stale_outputs() == []

        for _ in range(Output.STALE_MIN_OBSERVATIONS):
            light.process_matching_message(PHANTOM_S1)

        assert device.get_stale_outputs() == ["bathroom"]


class TestStaleLogging:
    def test_logs_warning_once_on_detection(self, caplog):
        """Detection logs a warning, and only on the transition."""
        _, light = _make_light()

        with caplog.at_level("WARNING"):
            for _ in range(Output.STALE_MIN_OBSERVATIONS * 3):
                light.process_matching_message(PHANTOM_S1)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "STALE" in warnings[0].message
        assert "242" in warnings[0].message

    def test_logs_info_on_recovery(self, caplog):
        """Recovery is logged."""
        _, light = _make_light()
        frame = Output.decode_output_frame(PHANTOM_S1, 0)

        for i in range(Output.STALE_MIN_OBSERVATIONS):
            light._note_stale_sample(frame, now=float(i))

        with caplog.at_level("INFO"):
            light.check_stale_recovery(now=Output.STALE_RECOVERY_SECONDS + 10)

        assert any("RECOVERED" in r.message for r in caplog.records)
