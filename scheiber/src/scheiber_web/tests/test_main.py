import scheiber_web.__main__ as web_main


class FakeRuntimeController:
    def __init__(self, settings):
        self.settings = settings
        self.started = False

    def start(self):
        self.started = True


class FakeApp:
    def __init__(self):
        self.run_calls = []

    def run(self, **kwargs):
        self.run_calls.append(kwargs)


def test_main_defaults_to_loopback_binding(monkeypatch):
    fake_app = FakeApp()
    captured = {}

    def fake_create_app(settings, runtime_controller):
        captured["settings"] = settings
        captured["runtime_controller"] = runtime_controller
        return fake_app

    monkeypatch.setattr(web_main, "BridgeRuntimeController", FakeRuntimeController)
    monkeypatch.setattr(web_main, "create_app", fake_create_app)

    exit_code = web_main.main(["--can-interface", "can1", "--mqtt-host", "localhost"])

    assert exit_code == 0
    assert captured["settings"].host == "127.0.0.1"
    assert captured["runtime_controller"].started is True
    assert fake_app.run_calls == [
        {
            "host": "127.0.0.1",
            "port": 8099,
            "threaded": True,
            "use_reloader": False,
        }
    ]


def test_main_allows_explicit_network_binding(monkeypatch):
    fake_app = FakeApp()
    captured = {}

    def fake_create_app(settings, runtime_controller):
        captured["settings"] = settings
        captured["runtime_controller"] = runtime_controller
        return fake_app

    monkeypatch.setattr(web_main, "BridgeRuntimeController", FakeRuntimeController)
    monkeypatch.setattr(web_main, "create_app", fake_create_app)

    exit_code = web_main.main(
        [
            "--can-interface",
            "can1",
            "--mqtt-host",
            "localhost",
            "--host",
            "0.0.0.0",
        ]
    )

    assert exit_code == 0
    assert captured["settings"].host == "0.0.0.0"
    assert captured["runtime_controller"].started is True
    assert fake_app.run_calls == [
        {
            "host": "0.0.0.0",
            "port": 8099,
            "threaded": True,
            "use_reloader": False,
        }
    ]


def test_main_supports_mcp_without_web_ui(monkeypatch):
    fake_app = FakeApp()
    captured = {}

    def fake_create_app(settings, runtime_controller):
        captured["settings"] = settings
        captured["runtime_controller"] = runtime_controller
        return fake_app

    monkeypatch.setattr(web_main, "BridgeRuntimeController", FakeRuntimeController)
    monkeypatch.setattr(web_main, "create_app", fake_create_app)

    exit_code = web_main.main(
        [
            "--can-interface",
            "can1",
            "--mqtt-host",
            "localhost",
            "--disable-web-ui",
            "--enable-mcp-server",
        ]
    )

    assert exit_code == 0
    assert captured["settings"].web_ui_enabled is False
    assert captured["settings"].mcp_server_enabled is True
    assert captured["runtime_controller"].started is True
