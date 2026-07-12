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
            "timeout_seconds": 900,
            "last_client_seen_at": 1.0,
            "clients": [{"client_id": client_id, "page": page, "last_seen_at": 1.0}],
        }

    def disconnect(self, client_id):
        self.disconnects.append(client_id)
        return {
            "active_clients": 0,
            "timeout_seconds": 900,
            "last_client_seen_at": 1.0,
            "clients": [],
        }

    def snapshot(self):
        return {
            "active_clients": 0,
            "timeout_seconds": 900,
            "last_client_seen_at": None,
            "clients": [],
        }


class FakeSetupHelper:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.start_calls = []
        self.run_calls = []
        self.stop_calls = 0

    def snapshot(self):
        return {
            "status": "idle",
            "target_name": "",
            "entity_id": None,
            "target_role": "light",
            "created_at": None,
            "known_output_count": 0,
            "phase": "idle",
            "instruction": "Start a setup helper session to begin guided discovery.",
            "active_run": None,
            "completed_run": None,
        }

    def start_session(self, name, *, entity_id=None, role="light"):
        if self.should_fail:
            raise RuntimeError("bridge not running")
        self.start_calls.append({"name": name, "entity_id": entity_id, "role": role})
        payload = self.snapshot()
        payload.update(
            {
                "status": "ready",
                "target_name": name or "",
                "entity_id": entity_id,
                "target_role": role,
                "phase": "ready",
            }
        )
        return payload

    def arm_run(self, action):
        self.run_calls.append(action)
        payload = self.snapshot()
        payload.update(
            {
                "status": "running",
                "phase": "countdown",
                "active_run": {
                    "action": action,
                    "countdown": 5,
                    "captured_message_count": 0,
                    "started_at": 1,
                    "press_at": 6,
                    "release_at": 6,
                    "capture_end_at": 9,
                },
            }
        )
        return payload

    def stop(self):
        self.stop_calls += 1
        return self.snapshot()


class FakeInteractionDiscovery:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.start_calls = []
        self.stop_calls = 0
        self.next_step_calls = 0
        self.previous_step_calls = 0
        self.finish_calls = 0
        self._status = "idle"
        self._location = ""
        self._button_count = None
        self._current_step_index = 0
        self._steps = []

    def snapshot(self):
        return {
            "status": self._status,
            "location": self._location,
            "button_count": self._button_count,
            "started_at": None,
            "last_message_at": None,
            "current_step_index": self._current_step_index,
            "current_step": (
                self._steps[self._current_step_index] if self._steps else None
            ),
            "is_first_step": self._current_step_index <= 0,
            "is_last_step": self._current_step_index >= len(self._steps) - 1,
            "steps": self._steps,
            "saved_at": None,
            "saved_path": None,
        }

    def recent_sessions(self):
        return []

    def start(self, location, button_count):
        if self.should_fail:
            raise RuntimeError("bridge not running")
        cleaned = str(location or "").strip()
        if not cleaned:
            raise ValueError("location is required")
        if button_count not in (2, 4):
            raise ValueError("button_count must be 2 or 4")
        self.start_calls.append((cleaned, button_count))
        self._status = "running"
        self._location = cleaned
        self._button_count = button_count
        self._current_step_index = 0
        keys = (
            ["top", "bottom"]
            if button_count == 2
            else [
                "top_left",
                "bottom_left",
                "top_right",
                "bottom_right",
            ]
        )
        self._steps = [
            {
                "key": key,
                "label": key.replace("_", " ").title(),
                "instruction": f"Press {key}",
                "event_count": 0,
                "reaction_count": 0,
                "companion_count": 0,
                "recent_events": [],
                "recent_reactions": [],
                "confirmed_air_switch": None,
                "suggested_config": None,
            }
            for key in keys
        ]
        return self.snapshot()

    def next_step(self):
        if not self._steps:
            raise RuntimeError("No interaction session is active; start one first")
        if self._current_step_index >= len(self._steps) - 1:
            raise ValueError("Already on the last step; use finish instead")
        self.next_step_calls += 1
        self._current_step_index += 1
        return self.snapshot()

    def previous_step(self):
        if not self._steps:
            raise RuntimeError("No interaction session is active; start one first")
        if self._current_step_index <= 0:
            raise ValueError("Already on the first step")
        self.previous_step_calls += 1
        self._current_step_index -= 1
        return self.snapshot()

    def finish(self):
        if not self._steps:
            raise RuntimeError("No interaction session is active; start one first")
        self.finish_calls += 1
        self._status = "complete"
        return self.snapshot()

    def stop(self):
        self.stop_calls += 1
        if self._status == "running":
            self._status = "stopped"
        return self.snapshot()


def create_test_client(
    tmp_path,
    runtime_controller=None,
    discovery_service=None,
    inspector=None,
    frontend_monitor=None,
    setup_helper=None,
    interaction_discovery=None,
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
        setup_helper=setup_helper or FakeSetupHelper(),
        interaction_discovery=interaction_discovery or FakeInteractionDiscovery(),
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
    assert 'data-tab="helper"' in page


def test_index_page_exposes_direct_base_path(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'window.ScheiberWebBasePath = "/";' in page
    assert 'src="/static/paths.js"' in page


def test_index_page_exposes_ingress_aware_base_path(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.get("/", headers={"X-Ingress-Path": "/abc123_scheiber"})

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'window.ScheiberWebBasePath = "/abc123_scheiber/";' in page
    assert 'src="/abc123_scheiber/static/paths.js"' in page


def test_embedded_inspect_page_exposes_direct_base_path(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.get("/inspect?embedded=1")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'window.ScheiberWebBasePath = "/";' in page
    assert 'src="/static/paths.js"' in page


def test_embedded_inspect_page_hides_back_link(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.get("/inspect?embedded=1")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "inspect-embedded" in page
    assert "Back to Setup" not in page
    assert 'id="inspect-data-format"' in page
    assert "Unsigned decimal" in page


def test_embedded_inspect_page_exposes_ingress_aware_base_path(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.get(
        "/inspect?embedded=1", headers={"X-Ingress-Path": "/abc123_scheiber"}
    )

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'window.ScheiberWebBasePath = "/abc123_scheiber/";' in page
    assert 'src="/abc123_scheiber/static/paths.js"' in page


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


def test_setup_helper_session_starts(tmp_path):
    setup_helper = FakeSetupHelper()
    client, _ = create_test_client(tmp_path, setup_helper=setup_helper)

    response = client.post(
        "/api/setup-helper/session",
        json={
            "name": "Underwater Light",
            "entity_id": "underwater_light",
            "role": "light",
        },
    )

    assert response.status_code == 200
    assert setup_helper.start_calls == [
        {
            "name": "Underwater Light",
            "entity_id": "underwater_light",
            "role": "light",
        }
    ]
    assert response.get_json()["target_name"] == "Underwater Light"


def test_setup_helper_session_starts_without_name(tmp_path):
    setup_helper = FakeSetupHelper()
    client, _ = create_test_client(tmp_path, setup_helper=setup_helper)

    response = client.post(
        "/api/setup-helper/session",
        json={"role": "light"},
    )

    assert response.status_code == 200
    assert setup_helper.start_calls == [
        {
            "name": None,
            "entity_id": None,
            "role": "light",
        }
    ]
    assert response.get_json()["target_name"] == ""


def test_setup_helper_run_starts_countdown(tmp_path):
    setup_helper = FakeSetupHelper()
    client, _ = create_test_client(tmp_path, setup_helper=setup_helper)

    response = client.post("/api/setup-helper/run", json={"action": "tap"})

    assert response.status_code == 200
    assert setup_helper.run_calls == ["tap"]
    assert response.get_json()["active_run"]["countdown"] == 5


def test_setup_helper_session_accepts_pulse_role(tmp_path):
    setup_helper = FakeSetupHelper()
    client, _ = create_test_client(tmp_path, setup_helper=setup_helper)

    response = client.post(
        "/api/setup-helper/session",
        json={
            "name": "Flybridge Door",
            "entity_id": "flybridge_door_close",
            "role": "pulse",
        },
    )

    assert response.status_code == 200
    assert setup_helper.start_calls[-1]["role"] == "pulse"


def test_interaction_discovery_starts_with_location(tmp_path):
    interaction_discovery = FakeInteractionDiscovery()
    client, _ = create_test_client(
        tmp_path, interaction_discovery=interaction_discovery
    )

    response = client.post(
        "/api/interactions/start",
        json={"location": "saloon entrance", "button_count": 4},
    )

    assert response.status_code == 200
    assert interaction_discovery.start_calls == [("saloon entrance", 4)]
    body = response.get_json()
    assert body["status"] == "running"
    assert [step["key"] for step in body["steps"]] == [
        "top_left",
        "bottom_left",
        "top_right",
        "bottom_right",
    ]


def test_interaction_discovery_requires_location(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.post(
        "/api/interactions/start", json={"location": "", "button_count": 2}
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_request"


def test_interaction_discovery_requires_valid_button_count(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.post(
        "/api/interactions/start",
        json={"location": "saloon entrance", "button_count": 3},
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_request"


def test_interaction_discovery_start_reports_runtime_conflict(tmp_path):
    client, _ = create_test_client(
        tmp_path,
        interaction_discovery=FakeInteractionDiscovery(should_fail=True),
    )

    response = client.post(
        "/api/interactions/start",
        json={"location": "saloon entrance", "button_count": 2},
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "runtime_not_running"


def test_interaction_discovery_next_and_previous_step(tmp_path):
    interaction_discovery = FakeInteractionDiscovery()
    client, _ = create_test_client(
        tmp_path, interaction_discovery=interaction_discovery
    )
    client.post(
        "/api/interactions/start",
        json={"location": "bow salon door", "button_count": 2},
    )

    next_response = client.post("/api/interactions/next-step")
    assert next_response.status_code == 200
    assert next_response.get_json()["current_step_index"] == 1
    assert interaction_discovery.next_step_calls == 1

    previous_response = client.post("/api/interactions/previous-step")
    assert previous_response.status_code == 200
    assert previous_response.get_json()["current_step_index"] == 0
    assert interaction_discovery.previous_step_calls == 1


def test_interaction_discovery_next_step_without_session_reports_conflict(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.post("/api/interactions/next-step")

    assert response.status_code == 409
    assert response.get_json()["code"] == "no_active_session"


def test_interaction_discovery_finish_marks_session_complete(tmp_path):
    interaction_discovery = FakeInteractionDiscovery()
    client, _ = create_test_client(
        tmp_path, interaction_discovery=interaction_discovery
    )
    client.post(
        "/api/interactions/start",
        json={"location": "bow salon door", "button_count": 2},
    )

    response = client.post("/api/interactions/finish")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "complete"
    assert body["recent_sessions"] == []
    assert interaction_discovery.finish_calls == 1


def test_get_interactions_includes_recent_sessions(tmp_path):
    client, _ = create_test_client(tmp_path)

    response = client.get("/api/interactions")

    assert response.status_code == 200
    assert response.get_json()["recent_sessions"] == []


def test_setup_helper_apply_updates_multiple_outputs_as_one_logical_light(tmp_path):
    runtime = FakeRuntimeController()
    client, config_path = create_test_client(tmp_path, runtime_controller=runtime)

    payload = client.get("/api/config").get_json()
    response = client.post(
        "/api/setup-helper/apply",
        json={
            "base_revision": payload["revision"],
            "role": "light",
            "entity_id": "underwater_light",
            "output_name": "Underwater Light",
            "device_names": {"8": "Aft panel"},
            "outputs": [
                {"bus_id": 7, "segment_id": 0, "output_name": "s1"},
                {"bus_id": 8, "segment_id": 0, "output_name": "s2"},
            ],
        },
    )

    assert response.status_code == 200
    saved_text = Path(config_path).read_text(encoding="utf-8")
    assert saved_text.count("entity_id: underwater_light") == 2
    assert "Underwater Light" in saved_text
    assert "name: Aft panel" in saved_text


def test_setup_helper_apply_accepts_pulse_role(tmp_path):
    runtime = FakeRuntimeController()
    client, config_path = create_test_client(tmp_path, runtime_controller=runtime)

    payload = client.get("/api/config").get_json()
    response = client.post(
        "/api/setup-helper/apply",
        json={
            "base_revision": payload["revision"],
            "role": "pulse",
            "entity_id": "flybridge_door_close",
            "output_name": "Flybridge Door Close",
            "device_names": {},
            "outputs": [{"bus_id": 7, "segment_id": 0, "output_name": "s2"}],
        },
    )

    assert response.status_code == 200
    saved_text = Path(config_path).read_text(encoding="utf-8")
    assert "pulses:" in saved_text
    assert "flybridge_door_close" in saved_text


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


def test_discovery_control_ignores_brightness_for_pulse_role(tmp_path):
    runtime = FakeRuntimeController()
    client, _ = create_test_client(tmp_path, runtime_controller=runtime)

    response = client.post(
        "/api/discovery/control",
        json={
            "bus_id": 3,
            "switch_nr": 0,
            "role": "pulse",
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


def test_bloc7_raw_candidate_exposes_voltage_suggestion(tmp_path):
    client, _ = create_test_client(tmp_path)
    inspector = client.application.config["INSPECTOR"]
    inspector.start()
    inspector._handle_message(
        can.Message(
            arbitration_id=0x0206058B,
            data=bytes([0x00, 0x00, 0x00, 0x00, 0x01, 0x0C]),
            is_extended_id=True,
        )
    )

    response = client.get("/api/discovery/bloc7?start_if_needed=false")

    assert response.status_code == 200
    candidates = response.get_json()["candidates"]
    raw_candidate = next(
        candidate
        for candidate in candidates
        if candidate["arbitration_id"] == "0x0206058B"
    )
    voltage = next(
        sensor
        for sensor in raw_candidate["suggested_sensors"]
        if sensor["sensor_type"] == "voltage"
    )
    assert voltage["label"] == "Battery-style voltage bytes 4-5"
    assert voltage["value_config"] == {
        "start_byte": 4,
        "bit_length": 16,
        "endian": "big",
        "scale": 0.1,
    }
    assert voltage["current_value"] == 26.8


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
            "params": {"protocolVersion": "2025-11-25"},
        },
        headers={"MCP-Protocol-Version": "2025-11-25"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["result"]["protocolVersion"] == "2025-11-25"
    assert response.headers["MCP-Protocol-Version"] == "2025-11-25"
    assert response.headers["Cache-Control"] == "no-store"
    assert "prompts" in payload["result"]["capabilities"]
    assert "tools" in payload["result"]["capabilities"]
    assert "resources" in payload["result"]["capabilities"]


def test_mcp_get_route_returns_explicit_405_without_html_page(tmp_path):
    client, _ = create_test_client(tmp_path, mcp_server_enabled=True)

    response = client.get("/mcp")

    assert response.status_code == 405
    assert response.headers["Allow"] == "OPTIONS, POST"
    assert response.headers["MCP-Protocol-Version"] == "2025-11-25"
    assert response.get_data(as_text=True) == ""


def test_mcp_initialized_notification_returns_accepted(tmp_path):
    client, _ = create_test_client(tmp_path, mcp_server_enabled=True)

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
        headers={"MCP-Protocol-Version": "2025-11-25"},
    )

    assert response.status_code == 202
    assert response.headers["MCP-Protocol-Version"] == "2025-11-25"
    assert response.get_data(as_text=True) == ""


def test_mcp_prompts_list_returns_empty_prompt_catalog(tmp_path):
    client, _ = create_test_client(tmp_path, mcp_server_enabled=True)

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "prompts/list",
            "params": {},
        },
        headers={"MCP-Protocol-Version": "2025-11-25"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["result"]["prompts"] == []
    assert response.headers["MCP-Protocol-Version"] == "2025-11-25"


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
