"""Flask application factory for the Scheiber setup UI."""

from __future__ import annotations

import logging
from typing import Optional

from flask import Flask, jsonify, render_template, request

from scheiber.config import (
    ConfigRevisionConflictError,
    ConfigValidationError,
    load_editor_state,
    restore_editor_config,
    save_editor_config,
    validate_editor_config,
)

from .discovery import Bloc9DiscoveryService
from .runtime import BridgeRuntimeController, RuntimeSettings


def create_app(
    settings: RuntimeSettings,
    runtime_controller: Optional[BridgeRuntimeController] = None,
    discovery_service: Optional[Bloc9DiscoveryService] = None,
) -> Flask:
    """Create the Scheiber web application."""
    app = Flask(__name__)
    app.logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    runtime_controller = runtime_controller or BridgeRuntimeController(settings)
    discovery_service = discovery_service or Bloc9DiscoveryService(runtime_controller)

    app.config["SCHEIBER_SETTINGS"] = settings
    app.config["RUNTIME_CONTROLLER"] = runtime_controller
    app.config["DISCOVERY_SERVICE"] = discovery_service

    @app.before_request
    def set_ingress_script_name():
        """Set SCRIPT_NAME from the X-Ingress-Path header injected by HA ingress.

        Without this, url_for('static', ...) generates paths like /static/styles.css
        which the browser resolves against the HA root, not the ingress prefix.
        With SCRIPT_NAME set, Flask generates /0289ae68_scheiber/static/styles.css.
        """
        ingress_path = request.headers.get("X-Ingress-Path", "").rstrip("/")
        if ingress_path:
            request.environ["SCRIPT_NAME"] = ingress_path

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
        payload = request.get_json(silent=True) or {}
        timeout_seconds = payload.get("timeout_seconds")
        try:
            snapshot = discovery_service.start(timeout_seconds=timeout_seconds)
        except RuntimeError as exc:
            return jsonify({"error": str(exc), "code": "runtime_not_running"}), 409
        return jsonify(snapshot)

    @app.post("/api/discovery/stop")
    def stop_discovery():
        return jsonify(discovery_service.stop())

    return app
