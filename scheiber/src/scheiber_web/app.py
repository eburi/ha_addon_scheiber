"""Flask application factory for the Scheiber setup UI."""

from __future__ import annotations

import logging
from typing import Optional

from flask import Flask, abort, jsonify, render_template, request

from scheiber.config import (
    ConfigValidationError,
    load_editor_state,
    validate_editor_config,
)

from .config_ops import ConfigApplyError, apply_editor_config
from .discovery import Bloc9DiscoveryService
from .inspector import CanInspector
from .mcp import MCPRequestError, ScheiberMCPServer
from .runtime import BridgeRuntimeController, RuntimeSettings


class _IngressPathMiddleware:
    """WSGI middleware that reads HA's X-Ingress-Path header and sets SCRIPT_NAME.

    Flask creates its URL adapter (used by url_for) when the request context is
    pushed, before before_request hooks run.  SCRIPT_NAME must therefore be set
    at the WSGI layer so that url_for('static', ...) generates correctly prefixed
    URLs like /0289ae68_scheiber/static/styles.css instead of /static/styles.css.
    """

    def __init__(self, wsgi_app):
        self._wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        ingress_path = environ.get("HTTP_X_INGRESS_PATH", "").rstrip("/")
        if ingress_path:
            environ["SCRIPT_NAME"] = ingress_path
            # Strip the prefix from PATH_INFO if HA hasn't already done so.
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(ingress_path):
                environ["PATH_INFO"] = path_info[len(ingress_path) :] or "/"
        return self._wsgi_app(environ, start_response)


def create_app(
    settings: RuntimeSettings,
    runtime_controller: Optional[BridgeRuntimeController] = None,
    discovery_service: Optional[Bloc9DiscoveryService] = None,
) -> Flask:
    """Create the Scheiber web application."""
    app = Flask(__name__)
    app.logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    app.wsgi_app = _IngressPathMiddleware(app.wsgi_app)

    runtime_controller = runtime_controller or BridgeRuntimeController(settings)
    discovery_service = discovery_service or Bloc9DiscoveryService(runtime_controller)
    inspector = CanInspector(runtime_controller)
    mcp_server = (
        ScheiberMCPServer(settings, runtime_controller, inspector)
        if settings.mcp_server_enabled
        else None
    )

    app.config["SCHEIBER_SETTINGS"] = settings
    app.config["RUNTIME_CONTROLLER"] = runtime_controller
    app.config["DISCOVERY_SERVICE"] = discovery_service
    app.config["INSPECTOR"] = inspector
    app.config["MCP_SERVER"] = mcp_server

    def require_web_ui() -> None:
        if not settings.web_ui_enabled:
            abort(404)

    @app.before_request
    def handle_options_preflight():
        """Return early for OPTIONS preflights (Chrome Private Network Access)."""
        if request.method == "OPTIONS":
            return "", 204

    @app.after_request
    def add_private_network_access(response):
        """Add headers required for Chrome's Private Network Access policy.

        Chrome treats HTTP (non-secure) pages as 'public' context and .local
        mDNS addresses as 'local' — public→local fetches are blocked unless the
        server responds with Access-Control-Allow-Private-Network: true.
        """
        origin = request.headers.get("Origin", "*")
        if request.method == "OPTIONS":
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Access-Control-Request-Private-Network"
            )
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

    @app.get("/")
    def index():
        require_web_ui()
        return render_template("index.html")

    @app.get("/api/status")
    def get_status():
        require_web_ui()
        config_state = load_editor_state(settings.config_path)
        return jsonify(
            {
                "runtime": runtime_controller.get_status(),
                "config": {
                    "status": config_state["status"],
                    "path": config_state["path"],
                    "revision": config_state["revision"],
                    "diagnostics": config_state["diagnostics"],
                },
            }
        )

    @app.get("/api/config")
    def get_config():
        require_web_ui()
        return jsonify(load_editor_state(settings.config_path))

    @app.post("/api/config/validate")
    def validate_config():
        require_web_ui()
        payload = request.get_json(silent=True) or {}
        try:
            normalized_config, warnings = validate_editor_config(payload.get("config"))
        except ConfigValidationError as exc:
            return (
                jsonify(
                    {
                        "valid": False,
                        "config": None,
                        "diagnostics": {
                            "errors": exc.errors,
                            "warnings": exc.warnings,
                        },
                    }
                ),
                422,
            )

        return jsonify(
            {
                "valid": True,
                "config": normalized_config,
                "diagnostics": {"errors": [], "warnings": warnings},
            }
        )

    @app.post("/api/config/apply")
    def apply_config():
        require_web_ui()
        payload = request.get_json(silent=True) or {}
        try:
            result = apply_editor_config(
                settings.config_path,
                runtime_controller,
                payload.get("config"),
                base_revision=payload.get("base_revision"),
            )
        except ConfigApplyError as exc:
            return jsonify(exc.to_response()), exc.status_code

        return jsonify(result)

    @app.get("/api/discovery")
    def get_discovery():
        require_web_ui()
        return jsonify(discovery_service.snapshot())

    @app.post("/api/discovery/start")
    def start_discovery():
        require_web_ui()
        try:
            snapshot = discovery_service.start()
        except RuntimeError as exc:
            return jsonify({"error": str(exc), "code": "runtime_not_running"}), 409
        return jsonify(snapshot)

    @app.post("/api/discovery/stop")
    def stop_discovery():
        require_web_ui()
        return jsonify(discovery_service.stop())

    @app.post("/api/discovery/control")
    def discovery_control():
        """Send a live CAN command to a Bloc9 output for testing purposes."""
        require_web_ui()
        if not runtime_controller.has_live_runtime():
            return (
                jsonify(
                    {"error": "Bridge is not running", "code": "runtime_not_running"}
                ),
                409,
            )

        payload = request.get_json(silent=True) or {}
        bus_id = payload.get("bus_id")
        segment_id = payload.get("segment_id", 0)
        if segment_id is None:
            segment_id = 0
        switch_nr = payload.get("switch_nr")
        on = payload.get("on", False)
        brightness = payload.get("brightness")

        if bus_id is None or switch_nr is None:
            return jsonify({"error": "bus_id and switch_nr are required"}), 400

        try:
            can_id = runtime_controller.send_bloc9_command(
                int(bus_id),
                int(switch_nr),
                bool(on),
                int(brightness) if brightness is not None else None,
                int(segment_id),
            )
        except RuntimeError as exc:
            return jsonify({"error": str(exc), "code": "runtime_not_running"}), 409
        except ValueError as exc:
            return jsonify({"error": str(exc), "code": "invalid_request"}), 400
        except Exception as exc:
            return jsonify({"error": str(exc), "code": "send_failed"}), 500

        return jsonify(
            {
                "sent": True,
                "bus_id": int(bus_id),
                "segment_id": int(segment_id),
                "switch_nr": int(switch_nr),
                "can_id": f"0x{can_id:08X}",
            }
        )

    @app.get("/inspect")
    def inspect_page():
        require_web_ui()
        return render_template("inspect.html")

    @app.get("/api/inspect")
    def get_inspect():
        require_web_ui()
        return jsonify(inspector.snapshot())

    @app.post("/api/inspect/start")
    def start_inspect():
        require_web_ui()
        if not runtime_controller.has_live_runtime():
            return (
                jsonify(
                    {"error": "Bridge is not running", "code": "runtime_not_running"}
                ),
                409,
            )
        return jsonify(inspector.start())

    @app.post("/api/inspect/stop")
    def stop_inspect():
        require_web_ui()
        return jsonify(inspector.stop())

    @app.get("/api/inspect/detail/<hex_id>")
    def get_inspect_detail(hex_id):
        require_web_ui()
        try:
            arb_id = int(hex_id, 16)
        except ValueError:
            abort(400)
        result = inspector.detail(arb_id)
        if result is None:
            abort(404)
        return jsonify(result)

    @app.post("/mcp")
    def mcp():
        if mcp_server is None:
            abort(404)

        payload = request.get_json(silent=True)
        if payload is None:
            error = MCPRequestError(
                -32700,
                "Request body must be valid JSON",
                http_status=400,
            )
            return jsonify(error.to_response()), error.http_status

        try:
            handled = mcp_server.handle_request(payload)
        except MCPRequestError as exc:
            return jsonify(exc.to_response()), exc.http_status

        if handled is None:
            return "", 202

        response, status_code = handled
        return jsonify(response), status_code

    return app
