import json

import can
import pytest
from scheiber_web.interactions import STEP_SEQUENCES, InteractionDiscoveryService

from scheiber.button_discovery import classify_button_source_message


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


def _wireless_frame(status_byte, identity="52AB81"):
    return can.Message(
        arbitration_id=0x04001A80,
        data=bytes.fromhex(f"01{identity}{status_byte:02X}"),
        is_extended_id=True,
    )


def test_classify_wireless_button_press_payload():
    message = can.Message(
        arbitration_id=0x04001A80,
        data=bytes([0x01, 0x54, 0x45, 0x1F, 0x82]),
        is_extended_id=True,
    )

    observation = classify_button_source_message(message)

    assert observation["source_family"] == "wireless_light_air_switch_interface"
    assert observation["identity_hex"] == "0154451F"
    assert observation["status_hex"] == "0x82"
    assert observation["active_bits"] == [1, 7]
    assert observation["lower_active_bits"] == [1]
    assert observation["high_bit_set"] is True


def test_start_requires_running_bridge():
    class StoppedRuntime(FakeRuntimeController):
        def has_live_runtime(self):
            return False

    service = InteractionDiscoveryService(StoppedRuntime())

    with pytest.raises(RuntimeError, match="bridge must be running"):
        service.start("galley", 2)


def test_start_requires_location():
    service = InteractionDiscoveryService(FakeRuntimeController())

    with pytest.raises(ValueError, match="location is required"):
        service.start("", 2)


@pytest.mark.parametrize("bad_count", [0, 1, 3, 5, "not-a-number", None])
def test_start_requires_valid_button_count(bad_count):
    service = InteractionDiscoveryService(FakeRuntimeController())

    with pytest.raises(ValueError, match="button_count must be 2 or 4"):
        service.start("galley", bad_count)


def test_start_builds_four_function_step_sequence():
    service = InteractionDiscoveryService(FakeRuntimeController())

    snapshot = service.start("bow salon door", 4)

    assert snapshot["status"] == "running"
    assert snapshot["button_count"] == 4
    assert [step["key"] for step in snapshot["steps"]] == [
        "top_left",
        "bottom_left",
        "top_right",
        "bottom_right",
    ]
    assert snapshot["current_step_index"] == 0
    assert snapshot["is_first_step"] is True
    assert snapshot["is_last_step"] is False


def test_start_builds_two_function_step_sequence():
    service = InteractionDiscoveryService(FakeRuntimeController())

    snapshot = service.start("crew cabin", 2)

    assert [step["key"] for step in snapshot["steps"]] == ["top", "bottom"]


def test_events_are_recorded_under_the_current_step():
    runtime = FakeRuntimeController()
    service = InteractionDiscoveryService(runtime)
    service.start("bow salon door", 4)

    service._handle_message(_wireless_frame(0x82))  # top_left press

    snapshot = service.snapshot()
    assert snapshot["current_step"]["key"] == "top_left"
    assert snapshot["current_step"]["event_count"] == 1
    event = snapshot["current_step"]["recent_events"][0]
    assert event["confirmed_air_switch"]["button_index"] == 2
    assert event["confirmed_air_switch"]["pressed"] is True


def test_next_and_previous_step_move_the_active_step():
    service = InteractionDiscoveryService(FakeRuntimeController())
    service.start("bow salon door", 4)

    service._handle_message(_wireless_frame(0x82))  # recorded under top_left

    snapshot = service.next_step()
    assert snapshot["current_step_index"] == 1
    assert snapshot["current_step"]["key"] == "bottom_left"
    assert snapshot["current_step"]["event_count"] == 0

    service._handle_message(_wireless_frame(0x81))  # recorded under bottom_left

    snapshot = service.previous_step()
    assert snapshot["current_step_index"] == 0
    assert snapshot["steps"][0]["event_count"] == 1
    assert snapshot["steps"][1]["event_count"] == 1


def test_next_step_rejects_advancing_past_the_last_step():
    service = InteractionDiscoveryService(FakeRuntimeController())
    service.start("crew cabin", 2)

    service.next_step()
    with pytest.raises(ValueError, match="last step"):
        service.next_step()


def test_previous_step_rejects_going_before_the_first_step():
    service = InteractionDiscoveryService(FakeRuntimeController())
    service.start("crew cabin", 2)

    with pytest.raises(ValueError, match="first step"):
        service.previous_step()


def test_bloc9_reactions_are_recorded_under_the_current_step():
    service = InteractionDiscoveryService(FakeRuntimeController())
    service.start("bow salon door", 4)

    reaction = can.Message(
        arbitration_id=0x0216069A,
        data=bytes([0x00, 0x00, 0x01, 0x01, 0x62, 0x00, 0x11, 0x00]),
        is_extended_id=True,
    )
    service._handle_message(reaction)

    snapshot = service.snapshot()
    assert snapshot["current_step"]["reaction_count"] == 1
    recorded = snapshot["current_step"]["recent_reactions"][0]
    assert recorded["route_slug"] == "3_2"


def test_companion_frames_are_captured_separately():
    service = InteractionDiscoveryService(FakeRuntimeController())
    service.start("bow salon door", 4)

    companion = can.Message(
        arbitration_id=0x04020F81,
        data=bytes.fromhex("00FF002000000000"),
        is_extended_id=True,
    )
    service._handle_message(companion)

    snapshot = service.snapshot()
    assert snapshot["current_step"]["companion_count"] == 1
    assert snapshot["current_step"]["event_count"] == 0


def test_deferred_wired_family_is_not_confirmed_air_switch():
    service = InteractionDiscoveryService(FakeRuntimeController())
    service.start("electric console", 2)

    wired = can.Message(
        arbitration_id=0x04001808,
        data=bytes.fromhex("0000000185"),
        is_extended_id=True,
    )
    service._handle_message(wired)

    snapshot = service.snapshot()
    event = snapshot["current_step"]["recent_events"][0]
    assert event["confirmed_air_switch"] is None


def test_suggested_config_appears_once_confirmed_and_uses_location_and_step():
    service = InteractionDiscoveryService(FakeRuntimeController())
    service.start("bow salon door", 4)

    service._handle_message(_wireless_frame(0x82))

    suggested = service.snapshot()["current_step"]["suggested_config"]
    assert suggested["entity_id"] == "bow_salon_door_top_left"
    assert suggested["identity"] == "52AB81"
    assert suggested["button_index"] == 2
    assert 'identity: "52AB81"' in suggested["yaml"]


def test_finish_writes_a_jsonl_record_and_recent_sessions_reads_it_back(tmp_path):
    log_path = tmp_path / "interactions_log.jsonl"
    service = InteractionDiscoveryService(
        FakeRuntimeController(), log_file_path=str(log_path)
    )
    service.start("bow salon door", 2)
    service._handle_message(_wireless_frame(0x81))
    service.next_step()
    service._handle_message(_wireless_frame(0x01))

    snapshot = service.finish()

    assert snapshot["status"] == "complete"
    assert snapshot["saved_path"] == str(log_path)
    assert log_path.exists()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["location"] == "bow salon door"
    assert record["button_count"] == 2
    assert len(record["steps"]) == 2
    assert len(record["steps"][0]["events"]) == 1
    assert len(record["steps"][1]["events"]) == 1

    recent = service.recent_sessions()
    assert len(recent) == 1
    assert recent[0]["location"] == "bow salon door"
    assert recent[0]["total_events"] == 2


def test_finish_without_log_file_configured_does_not_raise(tmp_path):
    service = InteractionDiscoveryService(FakeRuntimeController())
    service.start("crew cabin", 2)

    snapshot = service.finish()

    assert snapshot["status"] == "complete"
    assert snapshot["saved_path"] is None
    assert service.recent_sessions() == []


def test_finish_appends_multiple_sessions(tmp_path):
    log_path = tmp_path / "interactions_log.jsonl"
    service = InteractionDiscoveryService(
        FakeRuntimeController(), log_file_path=str(log_path)
    )

    service.start("bow salon door", 2)
    service.finish()
    service.start("crew cabin", 4)
    service.finish()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    recent = service.recent_sessions()
    assert [entry["location"] for entry in recent] == ["bow salon door", "crew cabin"]


def test_stop_marks_running_session_as_stopped_without_saving(tmp_path):
    log_path = tmp_path / "interactions_log.jsonl"
    service = InteractionDiscoveryService(
        FakeRuntimeController(), log_file_path=str(log_path)
    )
    service.start("bow salon door", 2)

    snapshot = service.stop()

    assert snapshot["status"] == "stopped"
    assert not log_path.exists()


def test_snapshot_without_session_returns_idle_state():
    service = InteractionDiscoveryService(FakeRuntimeController())

    snapshot = service.snapshot()

    assert snapshot["status"] == "idle"
    assert snapshot["steps"] == []
    assert snapshot["current_step"] is None


def test_next_step_requires_active_session():
    service = InteractionDiscoveryService(FakeRuntimeController())

    with pytest.raises(RuntimeError, match="No interaction session"):
        service.next_step()


def test_step_sequences_cover_the_documented_vimar_layouts():
    assert [step["key"] for step in STEP_SEQUENCES[2]] == ["top", "bottom"]
    assert [step["key"] for step in STEP_SEQUENCES[4]] == [
        "top_left",
        "bottom_left",
        "top_right",
        "bottom_right",
    ]
