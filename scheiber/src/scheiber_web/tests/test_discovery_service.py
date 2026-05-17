import can
from scheiber_web.discovery import Bloc9DiscoveryService


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


def test_discovery_service_tracks_local_and_segmented_candidates_separately():
    runtime = FakeRuntimeController()
    service = Bloc9DiscoveryService(runtime)
    service.start()

    local_msg = can.Message(
        arbitration_id=0x02160698,
        data=bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]),
        is_extended_id=True,
    )
    segmented_msg = can.Message(
        arbitration_id=0x0216069A,
        data=bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00]),
        is_extended_id=True,
    )

    service._handle_message(local_msg)
    service._handle_message(segmented_msg)

    snapshot = service.snapshot()

    assert [candidate["candidate_key"] for candidate in snapshot["candidates"]] == [
        "3:0",
        "3:2",
    ]
    assert snapshot["candidates"][0]["is_segmented"] is False
    assert snapshot["candidates"][1]["is_segmented"] is True
    assert snapshot["candidates"][1]["segment_id"] == 2
    assert snapshot["candidates"][1]["route_slug"] == "3_2"
