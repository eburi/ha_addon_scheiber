from pathlib import Path

from scheiber_web.app import create_app
from scheiber_web.runtime import RuntimeSettings


class FakeRuntimeController:
    def __init__(self, fail_reload=False):
        self.fail_reload = fail_reload
        self.reload_calls = 0
        self.running = True

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


def create_test_client(tmp_path, runtime_controller=None, discovery_service=None):
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
    )
    app = create_app(
        settings,
        runtime_controller=runtime_controller or FakeRuntimeController(),
        discovery_service=discovery_service or FakeDiscoveryService(),
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
    assert payload["config"]["devices"][0]["outputs"]["s1"]["role"] == "light"


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
