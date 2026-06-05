import can

from scheiber_web.setup_helper import SetupHelperService


class FakeRuntimeController:
    def __init__(self):
        self.callbacks = []

    def has_live_runtime(self):
        return True

    def subscribe_to_messages(self, callback):
        self.callbacks.append(callback)

    def unsubscribe_from_messages(self, callback):
        if callback in self.callbacks:
            self.callbacks.remove(callback)


def test_setup_helper_detects_changed_output():
    runtime = FakeRuntimeController()
    service = SetupHelperService(runtime)
    service.start_session("Underwater Light")
    service.arm_run("tap")

    run = service._session["active_run"]
    run["capture_start_at"] = 0
    run["capture_end_at"] = 9999999999
    run["press_at"] = 0

    message = can.Message(
        arbitration_id=0x02160698,
        data=bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]),
        is_extended_id=True,
    )
    service._handle_message(message)
    run["capture_end_at"] = 0

    snapshot = service.snapshot()

    assert snapshot["completed_run"]["changed_outputs"][0]["route_slug"] == "3"
    assert snapshot["completed_run"]["changed_outputs"][0]["output_name"] == "s1"


def test_setup_helper_hold_marks_dimming_as_light():
    runtime = FakeRuntimeController()
    service = SetupHelperService(runtime)
    service.start_session("Reading Light")
    service.arm_run("hold")

    run = service._session["active_run"]
    run["capture_start_at"] = 0
    run["capture_end_at"] = 9999999999
    run["press_at"] = 0
    run["release_at"] = 0

    dim_low = can.Message(
        arbitration_id=0x021A0698,
        data=bytes([0x10, 0x00, 0x11, 0x01, 0x00, 0x00, 0x00, 0x00]),
        is_extended_id=True,
    )
    dim_high = can.Message(
        arbitration_id=0x021A0698,
        data=bytes([0x40, 0x00, 0x11, 0x01, 0x00, 0x00, 0x00, 0x00]),
        is_extended_id=True,
    )
    service._handle_message(dim_low)
    service._handle_message(dim_high)
    run["capture_end_at"] = 0

    snapshot = service.snapshot()

    assert snapshot["completed_run"]["suggested_role"] == "light"
    assert snapshot["completed_run"]["changed_outputs"][0]["dimming_observed"] is True


def test_setup_helper_tap_detects_pulse_output():
    runtime = FakeRuntimeController()
    service = SetupHelperService(runtime)

    baseline_message = can.Message(
        arbitration_id=0x02160698,
        data=bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
        is_extended_id=True,
    )
    service._handle_message(baseline_message)

    service.start_session("Flybridge Door", role="switch")
    service.arm_run("tap")

    run = service._session["active_run"]
    run["capture_start_at"] = 0
    run["capture_end_at"] = 9999999999
    run["press_at"] = 0

    on_message = can.Message(
        arbitration_id=0x02160698,
        data=bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]),
        is_extended_id=True,
    )
    off_message = can.Message(
        arbitration_id=0x02160698,
        data=bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
        is_extended_id=True,
    )
    service._handle_message(on_message)
    service._handle_message(off_message)
    run["capture_end_at"] = 0

    snapshot = service.snapshot()

    assert snapshot["completed_run"]["suggested_role"] == "pulse"
    assert snapshot["completed_run"]["changed_outputs"][0]["pulse_observed"] is True


def test_setup_helper_session_can_start_without_name():
    runtime = FakeRuntimeController()
    service = SetupHelperService(runtime)

    snapshot = service.start_session(role="switch")

    assert snapshot["target_name"] == ""
    assert snapshot["target_role"] == "switch"
