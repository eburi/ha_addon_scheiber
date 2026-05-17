import can
from scheiber_web.inspector import CanInspector


class FakeRuntimeController:
    class settings:
        can_interface = "can1"

    def subscribe_to_messages(self, _callback):
        return None

    def unsubscribe_from_messages(self, _callback):
        return None


def test_snapshot_includes_known_bloc9_state_summary():
    inspector = CanInspector(FakeRuntimeController())
    inspector.start()

    inspector._handle_message(
        can.Message(
            arbitration_id=0x0218068A,
            data=bytes([0x00, 0x00, 0x00, 0x00, 0x80, 0x00, 0x00, 0x01]),
            is_extended_id=True,
        )
    )

    entry = inspector.snapshot()["entries"][0]

    assert entry["is_known"] is True
    assert entry["known_kind"] == "bloc9_state_update"
    assert entry["known_messages"] == [
        "Bloc9 #1_2 state update",
        "S3: OFF, S4: ON, 50%",
    ]


def test_snapshot_includes_known_bloc9_command_summary():
    inspector = CanInspector(FakeRuntimeController())
    inspector.start()

    inspector._handle_message(
        can.Message(
            arbitration_id=0x02360689,
            data=bytes([0x03, 0x11, 0x00, 0x80]),
            is_extended_id=True,
        )
    )

    entry = inspector.snapshot()["entries"][0]

    assert entry["is_known"] is True
    assert entry["known_kind"] == "bloc9_command"
    assert entry["known_messages"] == [
        "Bloc9 #1_1 command",
        "S4: ON, 50%",
    ]


def test_snapshot_marks_unknown_messages():
    inspector = CanInspector(FakeRuntimeController())
    inspector.start()

    inspector._handle_message(
        can.Message(
            arbitration_id=0x123,
            data=bytes([0x01, 0x02]),
            is_extended_id=False,
        )
    )

    entry = inspector.snapshot()["entries"][0]

    assert entry["is_known"] is False
    assert entry["known_kind"] is None
    assert entry["known_messages"] == []
