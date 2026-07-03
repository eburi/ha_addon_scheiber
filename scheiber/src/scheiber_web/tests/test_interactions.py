import can

from scheiber.button_discovery import classify_button_source_message
from scheiber_web.interactions import InteractionDiscoveryService


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


def test_interaction_discovery_correlates_button_and_bloc9_reaction():
    runtime = FakeRuntimeController()
    service = InteractionDiscoveryService(runtime)

    baseline = can.Message(
        arbitration_id=0x021A06C0,
        data=bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
        is_extended_id=True,
    )
    service._handle_message(baseline)

    snapshot = service.start("staircase")
    assert snapshot["status"] == "running"

    press = can.Message(
        arbitration_id=0x04001A80,
        data=bytes([0x01, 0x53, 0xE8, 0x86, 0x83]),
        is_extended_id=True,
    )
    reaction = can.Message(
        arbitration_id=0x021A06C0,
        data=bytes([0x00, 0x00, 0x00, 0x00, 0x4C, 0x00, 0x11, 0x01]),
        is_extended_id=True,
    )
    release = can.Message(
        arbitration_id=0x04001A80,
        data=bytes([0x01, 0x53, 0xE8, 0x86, 0x03]),
        is_extended_id=True,
    )

    service._handle_message(press)
    service._handle_message(reaction)
    service._handle_message(release)

    snapshot = service.snapshot()

    assert snapshot["phase"] == "waiting_for_reaction"
    assert snapshot["button_candidates"][0]["identity_hex"] == "0153E886"
    assert snapshot["button_events"][0]["event_type"] == "initial_pressed"
    assert snapshot["button_events"][-1]["event_type"] == "key_up"
    assert snapshot["button_events"][-1]["falling_bits"] == [7]
    assert snapshot["reaction_outputs"][0]["route_slug"] == "8"
    assert snapshot["reaction_outputs"][0]["output_name"] == "s6"


def test_interaction_discovery_requires_running_runtime():
    class StoppedRuntime(FakeRuntimeController):
        def has_live_runtime(self):
            return False

    service = InteractionDiscoveryService(StoppedRuntime())

    try:
        service.start("galley")
    except RuntimeError as exc:
        assert "bridge must be running" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
