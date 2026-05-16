"""Flask application factory for the Scheiber setup UI."""

from __future__ import annotations

import logging
from typing import Optional

from flask import Flask, jsonify, render_template, request, abort

from scheiber.config import (
    ConfigRevisionConflictError,
    ConfigValidationError,
    load_editor_state,
    restore_editor_config,
    save_editor_config,
    validate_editor_config,
)

from .discovery import Bloc9DiscoveryService
from .inspector import CanInspector
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

    app.config["SCHEIBER_SETTINGS"] = settings
    app.config["RUNTIME_CONTROLLER"] = runtime_controller
    app.config["DISCOVERY_SERVICE"] = discovery_service
    app.config["INSPECTOR"] = inspector

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
        return render_template("index.html")

    @app.get("/api/status")
    def get_status():
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
        return jsonify(load_editor_state(settings.config_path))

    @app.post("/api/config/validate")
    def validate_config():
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
        payload = request.get_json(silent=True) or {}
        try:
            save_result = save_editor_config(
                settings.config_path,
                payload.get("config"),
                expected_revision=payload.get("base_revision"),
            )
        except ConfigRevisionConflictError as exc:
            return jsonify({"error": str(exc), "code": "revision_conflict"}), 409
        except ConfigValidationError as exc:
            return (
                jsonify(
                    {
                        "error": "Configuration validation failed",
                        "code": "validation_failed",
                        "diagnostics": {
                            "errors": exc.errors,
                            "warnings": exc.warnings,
                        },
                    }
                ),
                422,
            )

        try:
            runtime_controller.reload()
        except Exception as exc:
            restore_editor_config(
                settings.config_path,
                save_result["previous_raw_yaml"],
                save_result["previous_exists"],
            )
            rollback_error = None
            try:
                runtime_controller.reload()
            except Exception as rollback_exc:  # pragma: no cover
                rollback_error = str(rollback_exc)

            return (
                jsonify(
                    {
                        "error": "Bridge reload failed",
                        "code": "reload_failed",
                        "details": str(exc),
                        "rollback_error": rollback_error,
                    }
                ),
                500,
            )

        return jsonify(
            {
                "saved": True,
                "applied": True,
                "config": save_result["config"],
                "revision": save_result["revision"],
                "diagnostics": save_result["diagnostics"],
                "runtime": runtime_controller.get_status(),
            }
        )

    @app.get("/api/discovery")
    def get_discovery():
        return jsonify(discovery_service.snapshot())

    @app.post("/api/discovery/start")
    def start_discovery():
        try:
            snapshot = discovery_service.start()
        except RuntimeError as exc:
            return jsonify({"error": str(exc), "code": "runtime_not_running"}), 409
        return jsonify(snapshot)

    @app.post("/api/discovery/stop")
    def stop_discovery():
        return jsonify(discovery_service.stop())

    @app.post("/api/discovery/control")
    def discovery_control():
        """Send a live CAN command to a Bloc9 output for testing purposes."""
        if not runtime_controller.has_live_runtime():
            return (
                jsonify({"error": "Bridge is not running", "code": "runtime_not_running"}),
                409,
            )

        payload = request.get_json(silent=True) or {}
        bus_id = payload.get("bus_id")
        switch_nr = payload.get("switch_nr")
        on = payload.get("on", False)
        brightness = payload.get("brightness")

        if bus_id is None or switch_nr is None:
            return jsonify({"error": "bus_id and switch_nr are required"}), 400

        try:
            runtime_controller.send_bloc9_command(
                int(bus_id),
                int(switch_nr),
                bool(on),
                int(brightness) if brightness is not None else None,
            )
        except RuntimeError as exc:
            return jsonify({"error": str(exc), "code": "runtime_not_running"}), 409
        except Exception as exc:
            return jsonify({"error": str(exc), "code": "send_failed"}), 500

        return jsonify({"sent": True, "bus_id": bus_id, "switch_nr": switch_nr})

    @app.get("/inspect")
    def inspect_page():
        return render_template("inspect.html")

    @app.get("/api/inspect")
    def get_inspect():
        return jsonify(inspector.snapshot())

    @app.post("/api/inspect/start")
    def start_inspect():
        if not runtime_controller.has_live_runtime():
            return (
                jsonify({"error": "Bridge is not running", "code": "runtime_not_running"}),
                409,
            )
        return jsonify(inspector.start())

    @app.post("/api/inspect/stop")
    def stop_inspect():
        return jsonify(inspector.stop())

    @app.get("/api/inspect/detail/<hex_id>")
    def get_inspect_detail(hex_id):
        try:
            arb_id = int(hex_id, 16)
        except ValueError:
            abort(400)
        result = inspector.detail(arb_id)
        if result is None:
            abort(404)
        return jsonify(result)

    return app
