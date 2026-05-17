from types import SimpleNamespace

import pytest
from scheiber_web.runtime import BridgeRuntimeController, RuntimeSettings


class FakeCanBus:
    def __init__(self):
        self.messages = []

    def send_message(self, arbitration_id, data):
        self.messages.append((arbitration_id, data))


class FakeBridge:
    def __init__(self):
        self.system = SimpleNamespace(can_bus=FakeCanBus())


def make_controller(read_only=False):
    settings = RuntimeSettings(
        can_interface="can1",
        mqtt_host="localhost",
        read_only=read_only,
    )
    controller = BridgeRuntimeController(settings)
    controller._bridge = FakeBridge()
    return controller


def test_send_bloc9_command_uses_segment_id():
    controller = make_controller()

    can_id = controller.send_bloc9_command(
        bus_id=3,
        segment_id=2,
        switch_nr=0,
        on=True,
        brightness=255,
    )

    assert can_id == 0x0236069A
    assert controller._bridge.system.can_bus.messages == [
        (0x0236069A, bytes([0x00, 0x01, 0x00, 0x00]))
    ]


def test_send_bloc9_command_rejects_read_only_runtime():
    controller = make_controller(read_only=True)

    with pytest.raises(RuntimeError, match="read-only mode"):
        controller.send_bloc9_command(bus_id=3, switch_nr=0, on=True)
