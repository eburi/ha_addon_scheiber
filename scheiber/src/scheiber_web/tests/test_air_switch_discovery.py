import json

import can
from scheiber_web.air_switch_discovery import (
    AirSwitchDiscoveryService,
    default_index_label,
)


class FakeRuntimeController:
    def __init__(self):
        self.callbacks = []

    def has_live_runtime(self):
        return True

    def subscribe_to_messages(self, callback):
        self.callbacks.append(callback)


def _frame(status_hex):
    return can.Message(
        arbitration_id=0x04001A80,
        data=bytes.fromhex(f"0152AB81{status_hex}"),
        is_extended_id=True,
    )


def test_air_switch_discovery_persists_seen_identity_and_index(tmp_path):
    state_file = tmp_path / "air_switch_discovery.json"
    runtime = FakeRuntimeController()
    service = AirSwitchDiscoveryService(runtime, state_file_path=str(state_file))

    snapshot = service.start()
    assert snapshot["running"] is True
    assert len(runtime.callbacks) == 1

    runtime.callbacks[0](_frame("82"))
    runtime.callbacks[0](_frame("02"))

    snapshot = service.snapshot()
    assert snapshot["air_switches"][0]["identity"] == "52AB81"
    index = snapshot["air_switches"][0]["indexes"][0]
    assert index["index"] == 2
    assert index["press_count"] == 1
    assert index["release_count"] == 1

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["air_switches"]["52AB81"]["indexes"]["2"]["press_count"] == 1


def test_air_switch_discovery_ignores_frames_while_stopped(tmp_path):
    runtime = FakeRuntimeController()
    service = AirSwitchDiscoveryService(
        runtime, state_file_path=str(tmp_path / "state.json")
    )
    service.start()
    service.stop()

    runtime.callbacks[0](_frame("82"))

    assert service.snapshot()["air_switches"] == []


def test_default_index_labels_follow_observed_patterns():
    assert default_index_label({"1": {}, "2": {}}, 1) == "Bottom"
    assert default_index_label({"1": {}, "2": {}}, 2) == "Top"
    assert (
        default_index_label({"1": {}, "2": {}, "3": {}, "4": {}}, 3) == "Bottom Right"
    )
    assert default_index_label({"1": {}, "2": {}, "3": {}, "4": {}}, 4) == "Top Right"
    assert default_index_label({"5": {}}, 5) == "Index 5"
