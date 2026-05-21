from pathlib import Path

import can
from scheiber_web.app import create_app
from scheiber_web.runtime import RuntimeSettings

from scheiber.config import load_editor_state


class FakeRuntimeController:
    def __init__(self, fail_reload=False):
        self.fail_reload = fail_reload
        self.reload_calls = 0
        self.running = True
        self.sent_commands = []

    def get_status(self):
        return {
            "running": self.running,
            "last_error": None,
            "started_at": None,
            "last_reload_at": None,
            "can_interface": "can1",
            "mqtt_host": "localhost",
            "mqtt_port": 1883,
            "config_path": "/tmp/config.yaml",
            "effective_config_path": "/tmp/config.yaml",
            "config_exists": True,
            "state_file": None,
            "read_only": False,
            "web_ui_enabled": True,
            "mcp_server_enabled": False,
        }

    def reload(self):
        self.reload_calls += 1
        if self.fail_reload:
            raise RuntimeError("reload failed")

    def has_live_runtime(self):
        return self.running

    def subscribe_to_messages(self, _callback):
        return None

    def unsubscribe_from_messages(self, _callback):
        return None

    def send_bloc9_command(self, bus_id, switch_nr, on, brightness=None, segment_id=0):
        self.sent_commands.append(
            {
                "bus_id": bus_id,
                "switch_nr": switch_nr,
                "on": on,
                "brightness": brightness,
                "segment_id": segment_id,
            }
        )
        return 0x02360600 | (0x80 | (bus_id << 3) | segment_id)


class FakeDiscoveryService:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail

    def snapshot(self):
        return {
            "status": "idle",
            "started_at": None,
            "last_message_at": None,
            "timeout_seconds": 60,
            "message_counts": {"state_update": 0, "heartbeat": 0},
            "candidates": [],
        }

    def start(self, timeout_seconds=None):
        if self.should_fail:
            raise RuntimeError("bridge not running")
        return {
            "status": "running",
            "started_at": 1,
            "last_message_at": None,
            "timeout_seconds": timeout_seconds or 60,
            "message_counts": {"state_update": 0, "heartbeat": 0},
            "candidates": [],
        }

    def stop(self):
        return self.snapshot()


class FakeInspector:
    def __init__(self):
        self.stop_calls = 0

    def snapshot(self):
        return {
            "status": "stopped",
            "can_interface": "can1",
            "started_at": None,
            "last_message_at": None,
            "total_messages": 0,
            "unique_ids": 0,
            "entries": [],
        }

    def start(self):
        return self.snapshot()

    def stop(self):
        self.stop_calls += 1
        return self.snapshot()

    def detail(self, _arb_id):
        return None


class FakeFrontendMonitor:
    def __init__(self):
        self.callbacks = []
        self.heartbeats = []
        self.disconnects = []

    def add_idle_callback(self, callback):
        self.callbacks.append(callback)

    def heartbeat(self, client_id, page=None):
        self.heartbeats.append({"client_id": client_id, "page": page})
        return {
            "active_clients": 1,
            "timeout_seconds": 15,
            "last_client_seen_at": 1.0,
            "clients": [{"client_id": client_id, "page": page, "last_seen_at": 1.0}],
        }

    def disconnect(self, client_id):
        self.disconnects.append(client_id)
        return {
            "active_clients": 0,
            "timeout_seconds": 15,
            "last_client_seen_at": 1.0,
            "clients": [],
        }

    def snapshot(self):
        return {
            "active_clients": 0,
            "timeout_seconds": 15,
            "last_client_seen_at": None,
            "clients": [],
        }


def create_test_client(
    tmp_path,
    runtime_controller=None,
    discovery_service=None,
    inspector=None,
    frontend_monitor=None,
    *,
    web_ui_enabled=True,
    mcp_server_enabled=False,
):
    config_path = tmp_path / "scheiber-config.yaml"
    config_path.write_text("""
devices:
  - type: bloc9
    bus_id: 7
    lights:
      s1:
        name: Main Light
        entity_id: main_light
""".strip())

    settings = RuntimeSettings(
        can_interface="can1",
        mqtt_host="localhost",
        config_path=str(config_path),
        web_ui_enabled=web_ui_enabled,
        mcp_server_enabled=mcp_server_enabled,
    )
    runtime = runtime_controller or FakeRuntimeController()
    runtime.settings = settings
    app = create_app(
        settings,
        runtime_controller=runtime,
        discovery_service=discovery_service or FakeDiscoveryService(),
        inspector=inspector,
        frontend_monitor=frontend_monitor or FakeFrontendMonitor(),
    )
    app.testing = True
    return app.test_client(), config_path


def test_get_config_returns_normalized_editor_payload(tmp_path):
    client, _config_path = create_test_client(tmp_path)

    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "valid"
    assert payload["config"]["devices"][0]["bus_id"] == 7
    assert payload["config"]["devices"][0]["segment_id"] == 0
    assert payload["config"]["devices"][0]["outputs"]["s1"]["role"] == "light"


def test_index_page_uses_setup_heading_and_tabbed_navigation(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "<h1>Setup</h1>" in page
    assert 'data-tab="bloc9"' in page
    assert 'data-tab="bloc7"' in page
    assert 'data-tab="inspect"' in page


def test_embedded_inspect_page_hides_back_link(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.get("/inspect?embedded=1")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "inspect-embedded" in page
    assert "Back to Setup" not in page
    assert 'id="inspect-data-format"' in page
    assert "Unsigned decimal" in page


def test_apply_config_saves_and_reloads_runtime(tmp_path):
    runtime = FakeRuntimeController()
    client, config_path = create_test_client(tmp_path, runtime_controller=runtime)

    payload = client.get("/api/config").get_json()
    config = payload["config"]
    config["devices"][0]["outputs"]["s2"] = {
        "enabled": True,
        "role": "switch",
        "name": "Pump",
        "entity_id": "pump_switch",
        "initial_brightness": None,
    }

    response = client.post(
        "/api/config/apply",
        json={"config": config, "base_revision": payload["revision"]},
    )

    assert response.status_code == 200
    assert runtime.reload_calls == 1
    saved_text = Path(config_path).read_text(encoding="utf-8")
    assert "pump_switch" in saved_text


def test_apply_config_preserves_named_disabled_outputs(tmp_path):
    runtime = FakeRuntimeController()
    client, config_path = create_test_client(tmp_path, runtime_controller=runtime)

    payload = client.get("/api/config").get_json()
    config = payload["config"]
    config["devices"][0]["outputs"]["s2"] = {
        "enabled": False,
        "role": None,
        "name": "Future cabin light",
        "entity_id": "",
        "initial_brightness": None,
    }

    response = client.post(
        "/api/config/apply",
        json={"config": config, "base_revision": payload["revision"]},
    )

    assert response.status_code == 200
    saved_text = Path(config_path).read_text(encoding="utf-8")
    assert "outputs:" in saved_text
    assert "Future cabin light" in saved_text
    assert "lights:" in saved_text

    refreshed = client.get("/api/config").get_json()
    assert (
        refreshed["config"]["devices"][0]["outputs"]["s2"]["name"]
        == "Future cabin light"
    )
    assert refreshed["config"]["devices"][0]["outputs"]["s2"]["enabled"] is False


def test_apply_config_saves_bloc7_sensor_device(tmp_path):
    runtime = FakeRuntimeController()
    client, config_path = create_test_client(tmp_path, runtime_controller=runtime)

    payload = client.get("/api/config").get_json()
    config = payload["config"]
    config["devices"].append(
        {
            "type": "bloc7",
            "bus_id": 21,
            "segment_id": 0,
            "name": "Tank bank",
            "description": "Manual matcher binding",
            "sensors": [
                {
                    "name": "Black water 1",
                    "entity_id": "black_water_1",
                    "sensor_type": "level",
                    "matcher": {
                        "pattern": 0x0204058A,
                        "mask": 0xFFFFFFFF,
                    },
                    "value_config": {
                        "start_byte": 3,
                        "bit_length": 8,
                        "endian": "little",
                        "scale": 1.0,
                    },
                }
            ],
        }
    )

    response = client.post(
        "/api/config/apply",
        json={"config": config, "base_revision": payload["revision"]},
    )

    assert response.status_code == 200
    saved_text = Path(config_path).read_text(encoding="utf-8")
    assert "type: bloc7" in saved_text
    assert "black_water_1" in saved_text


def test_apply_config_rolls_back_when_reload_fails(tmp_path):
    runtime = FakeRuntimeController(fail_reload=True)
    client, config_path = create_test_client(tmp_path, runtime_controller=runtime)

    original_text = config_path.read_text(encoding="utf-8")
    payload = client.get("/api/config").get_json()
    config = payload["config"]
    config["devices"][0]["bus_id"] = 8

    response = client.post(
        "/api/config/apply",
        json={"config": config, "base_revision": payload["revision"]},
    )

    assert response.status_code == 500
    assert runtime.reload_calls == 2
    assert config_path.read_text(encoding="utf-8") == original_text


def test_discovery_start_returns_conflict_when_runtime_is_unavailable(tmp_path):
    client, _config_path = create_test_client(
        tmp_path,
        discovery_service=FakeDiscoveryService(should_fail=True),
    )

    response = client.post("/api/discovery/start", json={"timeout_seconds": 10})

    assert response.status_code == 409
    assert response.get_json()["code"] == "runtime_not_running"


def test_frontend_heartbeat_updates_browser_session(tmp_path):
    frontend_monitor = FakeFrontendMonitor()
    client, _ = create_test_client(tmp_path, frontend_monitor=frontend_monitor)

    response = client.post(
        "/api/frontend/heartbeat",
        json={"client_id": "browser-1", "page": "setup"},
    )

    assert response.status_code == 200
    assert frontend_monitor.heartbeats == [{"client_id": "browser-1", "page": "setup"}]
    assert response.get_json()["active_clients"] == 1


def test_frontend_disconnect_requires_client_id(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.post("/api/frontend/disconnect", json={})

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_request"


def test_discovery_control_accepts_segment_id(tmp_path):
    runtime = FakeRuntimeController()
    client, _config_path = create_test_client(tmp_path, runtime_controller=runtime)

    response = client.post(
        "/api/discovery/control",
        json={
            "bus_id": 3,
            "segment_id": 2,
            "switch_nr": 0,
            "role": "light",
            "on": True,
            "brightness": 255,
        },
    )

    assert response.status_code == 200
    assert runtime.sent_commands == [
        {
            "bus_id": 3,
            "switch_nr": 0,
            "on": True,
            "brightness": 255,
            "segment_id": 2,
        }
    ]
    assert response.get_json()["can_id"] == "0x0236069A"


def test_discovery_control_defaults_segment_id_to_zero(tmp_path):
    runtime = FakeRuntimeController()
    client, _ = create_test_client(tmp_path, runtime_controller=runtime)

    response = client.post(
        "/api/discovery/control",
        json={
            "bus_id": 3,
            "switch_nr": 0,
            "role": "light",
            "on": True,
            "brightness": 255,
        },
    )

    assert response.status_code == 200
    assert runtime.sent_commands == [
        {
            "bus_id": 3,
            "switch_nr": 0,
            "on": True,
            "brightness": 255,
            "segment_id": 0,
        }
    ]
    assert response.get_json()["segment_id"] == 0
    assert response.get_json()["can_id"] == "0x02360698"


def test_discovery_control_ignores_brightness_for_switch_role(tmp_path):
    runtime = FakeRuntimeController()
    client, _ = create_test_client(tmp_path, runtime_controller=runtime)

    response = client.post(
        "/api/discovery/control",
        json={
            "bus_id": 3,
            "switch_nr": 0,
            "role": "switch",
            "on": True,
            "brightness": 64,
        },
    )

    assert response.status_code == 200
    assert runtime.sent_commands == [
        {
            "bus_id": 3,
            "switch_nr": 0,
            "on": True,
            "brightness": None,
            "segment_id": 0,
        }
    ]


def test_discovery_control_ignores_brightness_without_light_role(tmp_path):
    runtime = FakeRuntimeController()
    client, _ = create_test_client(tmp_path, runtime_controller=runtime)

    response = client.post(
        "/api/discovery/control",
        json={
            "bus_id": 3,
            "switch_nr": 0,
            "on": True,
            "brightness": 64,
        },
    )

    assert response.status_code == 200
    assert runtime.sent_commands == [
        {
            "bus_id": 3,
            "switch_nr": 0,
            "on": True,
            "brightness": None,
            "segment_id": 0,
        }
    ]


def test_discovery_control_rejects_invalid_role(tmp_path):
    runtime = FakeRuntimeController()
    client, _ = create_test_client(tmp_path, runtime_controller=runtime)

    response = client.post(
        "/api/discovery/control",
        json={
            "bus_id": 3,
            "switch_nr": 0,
            "role": "sensor",
            "on": True,
            "brightness": 64,
        },
    )

    assert response.status_code == 400
    assert runtime.sent_commands == []


def test_apply_config_persists_segment_id(tmp_path):
    runtime = FakeRuntimeController()
    client, config_path = create_test_client(tmp_path, runtime_controller=runtime)

    payload = client.get("/api/config").get_json()
    config = payload["config"]
    config["devices"][0]["segment_id"] = 3

    response = client.post(
        "/api/config/apply",
        json={"config": config, "base_revision": payload["revision"]},
    )

    assert response.status_code == 200
    saved_text = Path(config_path).read_text(encoding="utf-8")
    assert "segment_id: 3" in saved_text


def test_bloc7_discovery_endpoint_returns_candidates(tmp_path):
    client, _ = create_test_client(tmp_path)
    inspector = client.application.config["INSPECTOR"]
    inspector.start()
    inspector._handle_message(
        can.Message(
            arbitration_id=0x0204058A,
            data=bytes([0x00, 0x08, 0x00, 0x33, 0x00, 0x00, 0x00, 0x00]),
            is_extended_id=True,
        )
    )

    response = client.get("/api/discovery/bloc7?start_if_needed=false")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["candidates"]
    assert payload["candidates"][0]["arbitration_id"] == "0x0204058A"
    assert (
        payload["candidates"][0]["suggested_sensors"][0]["matcher"]["pattern"]
        == 0x0204058A
    )
    assert payload["candidates"][0]["suggested_sensors"][0]["current_value"] == 8


def test_discovery_endpoint_classifies_source_selector_ac_candidate(tmp_path):
    client, _ = create_test_client(tmp_path)
    inspector = client.application.config["INSPECTOR"]
    inspector.start()
    inspector._handle_message(
        can.Message(
            arbitration_id=0x02040B9A,
            data=bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0xEB, 0x00, 0x32]),
            is_extended_id=True,
        )
    )

    response = client.get("/api/discovery/bloc7?start_if_needed=false")

    assert response.status_code == 200
    candidates = response.get_json()["candidates"]
    selector = next(
        candidate
        for candidate in candidates
        if candidate["arbitration_id"] == "0x02040B9A"
    )
    assert selector["device_type"] == "source_selector"
    assert selector["family"] == "ac_measurement"
    assert {sensor["sensor_type"] for sensor in selector["suggested_sensors"]} == {
        "voltage",
        "frequency",
    }


def test_mcp_route_returns_404_when_disabled(tmp_path):
    client, _ = create_test_client(tmp_path, mcp_server_enabled=False)

    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})

    assert response.status_code == 404


def test_mcp_initialize_lists_capabilities(tmp_path):
    client, _ = create_test_client(tmp_path, mcp_server_enabled=True)

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["result"]["protocolVersion"] == "2025-03-26"
    assert "tools" in payload["result"]["capabilities"]
    assert "resources" in payload["result"]["capabilities"]


def test_mcp_save_config_applies_and_reloads_runtime(tmp_path):
    runtime = FakeRuntimeController()
    client, config_path = create_test_client(
        tmp_path,
        runtime_controller=runtime,
        mcp_server_enabled=True,
    )

    state = load_editor_state(str(config_path))
    config = state["config"]
    config["devices"][0]["outputs"]["s2"] = {
        "enabled": True,
        "role": "switch",
        "name": "Pump",
        "entity_id": "pump_switch",
        "initial_brightness": None,
    }

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "save_config",
                "arguments": {
                    "config": config,
                    "base_revision": state["revision"],
                },
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["result"]
    assert payload["isError"] is False
    assert payload["structuredContent"]["saved"] is True
    assert runtime.reload_calls == 1
    assert "pump_switch" in Path(config_path).read_text(encoding="utf-8")


def test_mcp_can_snapshot_starts_capture_when_needed(tmp_path):
    client, _ = create_test_client(tmp_path, mcp_server_enabled=True)

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "read_can_snapshot", "arguments": {}},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["result"]
    assert payload["isError"] is False
    assert payload["structuredContent"]["status"] == "running"


def test_mcp_detect_bloc7_candidates_returns_structured_payload(tmp_path):
    client, _ = create_test_client(tmp_path, mcp_server_enabled=True)
    inspector = client.application.config["INSPECTOR"]
    inspector.start()
    inspector._handle_message(
        can.Message(
            arbitration_id=0x02040582,
            data=bytes([0x00, 0x4D, 0x00, 0x00, 0x00, 0x38, 0x00, 0x00]),
            is_extended_id=True,
        )
    )

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "detect_bloc7_candidates",
                "arguments": {"start_if_needed": False},
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["result"]
    assert payload["isError"] is False
    assert payload["structuredContent"]["candidates"][0]["family"] == "normalized_level"


def test_mcp_detect_protocol_candidates_returns_source_selector(tmp_path):
    client, _ = create_test_client(tmp_path, mcp_server_enabled=True)
    inspector = client.application.config["INSPECTOR"]
    inspector.start()
    inspector._handle_message(
        can.Message(
            arbitration_id=0x02040BA9,
            data=bytes([0x00, 0xF0, 0x00, 0x32, 0x00, 0xF0, 0x00, 0x32]),
            is_extended_id=True,
        )
    )

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "detect_protocol_candidates",
                "arguments": {"start_if_needed": False},
            },
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["result"]
    assert payload["isError"] is False
    assert (
        payload["structuredContent"]["candidates"][0]["device_type"]
        == "source_selector"
    )


def test_web_ui_routes_return_404_when_disabled(tmp_path):
    client, _ = create_test_client(
        tmp_path, web_ui_enabled=False, mcp_server_enabled=True
    )

    response = client.get("/api/config")

    assert response.status_code == 404
