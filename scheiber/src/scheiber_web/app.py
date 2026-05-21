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

from .bloc7_candidates import build_bloc7_candidate_snapshot
from .config_ops import ConfigApplyError, apply_editor_config
from .discovery import Bloc9DiscoveryService
from .frontend_heartbeat import FrontendHeartbeatMonitor
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
    inspector: Optional[CanInspector] = None,
    frontend_monitor: Optional[FrontendHeartbeatMonitor] = None,
) -> Flask:
    """Create the Scheiber web application."""
    app = Flask(__name__)
    app.logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    app.wsgi_app = _IngressPathMiddleware(app.wsgi_app)

    runtime_controller = runtime_controller or BridgeRuntimeController(settings)
    discovery_service = discovery_service or Bloc9DiscoveryService(runtime_controller)
    inspector = inspector or CanInspector(runtime_controller)
    frontend_monitor = frontend_monitor or FrontendHeartbeatMonitor(logger=app.logger)
    frontend_monitor.add_idle_callback(discovery_service.stop)
    frontend_monitor.add_idle_callback(inspector.stop)
    mcp_server = (
        ScheiberMCPServer(settings, runtime_controller, inspector)
        if settings.mcp_server_enabled
        else None
    )

    app.config["SCHEIBER_SETTINGS"] = settings
    app.config["RUNTIME_CONTROLLER"] = runtime_controller
    app.config["DISCOVERY_SERVICE"] = discovery_service
    app.config["INSPECTOR"] = inspector
    app.config["FRONTEND_MONITOR"] = frontend_monitor
    app.config["MCP_SERVER"] = mcp_server

    def require_web_ui() -> None:
        if not settings.web_ui_enabled:
            abort(404)

    def resolve_mcp_protocol_version(payload=None, response_payload=None) -> str | None:
        request_version = request.headers.get("MCP-Protocol-Version")
        if (
            isinstance(payload, dict)
            and payload.get("method") == "initialize"
            and isinstance(response_payload, dict)
        ):
            result = response_payload.get("result")
            if isinstance(result, dict):
                response_version = result.get("protocolVersion")
                if isinstance(response_version, str):
                    return response_version

        if mcp_server is not None and mcp_server.supports_protocol_version(request_version):
            return request_version
        if mcp_server is not None:
            return mcp_server.latest_protocol_version()
        return None

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
                "frontend": frontend_monitor.snapshot(),
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

    @app.post("/api/frontend/heartbeat")
    def frontend_heartbeat():
        require_web_ui()
        payload = request.get_json(silent=True) or {}
        client_id = str(payload.get("client_id") or "").strip()
        if not client_id:
            return (
                jsonify({"error": "client_id is required", "code": "invalid_request"}),
                400,
            )

        return jsonify(
            frontend_monitor.heartbeat(
                client_id, page=str(payload.get("page") or "").strip() or None
            )
        )

    @app.post("/api/frontend/disconnect")
    def frontend_disconnect():
        require_web_ui()
        payload = request.get_json(silent=True) or {}
        client_id = str(payload.get("client_id") or "").strip()
        if not client_id:
            return (
                jsonify({"error": "client_id is required", "code": "invalid_request"}),
                400,
            )

        return jsonify(frontend_monitor.disconnect(client_id))

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

    @app.get("/api/discovery/bloc7")
    def get_bloc7_discovery():
        require_web_ui()
        if not runtime_controller.has_live_runtime():
            return (
                jsonify(
                    {"error": "Bridge is not running", "code": "runtime_not_running"}
                ),
                409,
            )
        start_if_needed = request.args.get("start_if_needed", "true").lower() != "false"
        return jsonify(
            build_bloc7_candidate_snapshot(inspector, start_if_needed=start_if_needed)
        )

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
        role = payload.get("role")

        if bus_id is None or switch_nr is None:
            return jsonify({"error": "bus_id and switch_nr are required"}), 400

        if role is None:
            normalized_role = None
        elif isinstance(role, str):
            normalized_role = role.strip().lower() or None
        else:
            return (
                jsonify({"error": "role must be 'light', 'switch', or omitted"}),
                400,
            )

        if normalized_role not in {None, "light", "switch"}:
            return (
                jsonify({"error": "role must be 'light', 'switch', or omitted"}),
                400,
            )

        allowed_brightness = brightness if normalized_role == "light" else None

        try:
            can_id = runtime_controller.send_bloc9_command(
                int(bus_id),
                int(switch_nr),
                bool(on),
                int(allowed_brightness) if allowed_brightness is not None else None,
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
        return render_template(
            "inspect.html", embedded=request.args.get("embedded") == "1"
        )

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

    @app.get("/mcp")
    def mcp_get():
        if mcp_server is None:
            abort(404)

        response = app.response_class(status=405)
        response.headers["Allow"] = "OPTIONS, POST"
        protocol_version = resolve_mcp_protocol_version()
        if protocol_version is not None:
            response.headers["MCP-Protocol-Version"] = protocol_version
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.delete("/mcp")
    def mcp_delete():
        if mcp_server is None:
            abort(404)

        response = app.response_class(status=405)
        response.headers["Allow"] = "OPTIONS, POST"
        protocol_version = resolve_mcp_protocol_version()
        if protocol_version is not None:
            response.headers["MCP-Protocol-Version"] = protocol_version
        response.headers["Cache-Control"] = "no-store"
        return response

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
            response = jsonify(error.to_response())
            response.status_code = error.http_status
            protocol_version = resolve_mcp_protocol_version()
            if protocol_version is not None:
                response.headers["MCP-Protocol-Version"] = protocol_version
            response.headers["Cache-Control"] = "no-store"
            return response

        try:
            handled = mcp_server.handle_request(payload)
        except MCPRequestError as exc:
            response = jsonify(exc.to_response())
            response.status_code = exc.http_status
            protocol_version = resolve_mcp_protocol_version(payload)
            if protocol_version is not None:
                response.headers["MCP-Protocol-Version"] = protocol_version
            response.headers["Cache-Control"] = "no-store"
            return response

        if handled is None:
            response = app.response_class(status=202)
            protocol_version = resolve_mcp_protocol_version(payload)
            if protocol_version is not None:
                response.headers["MCP-Protocol-Version"] = protocol_version
            response.headers["Cache-Control"] = "no-store"
            return response

        response, status_code = handled
        flask_response = jsonify(response)
        flask_response.status_code = status_code
        protocol_version = resolve_mcp_protocol_version(payload, response)
        if protocol_version is not None:
            flask_response.headers["MCP-Protocol-Version"] = protocol_version
        flask_response.headers["Cache-Control"] = "no-store"
        return flask_response

    return app
