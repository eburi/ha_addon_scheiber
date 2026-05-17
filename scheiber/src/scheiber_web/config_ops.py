"""Shared configuration persistence helpers for the management runtime."""

from __future__ import annotations

from typing import Any, Dict, Optional

from scheiber.config import (
    ConfigRevisionConflictError,
    ConfigValidationError,
    restore_editor_config,
    save_editor_config,
)


class ConfigApplyError(RuntimeError):
    """Raised when a config apply operation cannot complete cleanly."""

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int,
        diagnostics: Optional[Dict[str, Any]] = None,
        details: Optional[str] = None,
        rollback_error: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.diagnostics = diagnostics
        self.details = details
        self.rollback_error = rollback_error

    def to_response(self) -> Dict[str, Any]:
        """Return the JSON payload used by HTTP/MCP callers."""
        payload: Dict[str, Any] = {"error": str(self), "code": self.code}
        if self.diagnostics is not None:
            payload["diagnostics"] = self.diagnostics
        if self.details is not None:
            payload["details"] = self.details
        if self.rollback_error is not None:
            payload["rollback_error"] = self.rollback_error
        return payload


def apply_editor_config(
    config_path: str,
    runtime_controller,
    config: Dict[str, Any],
    base_revision: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate, persist, and hot-reload editor config through the runtime."""
    try:
        save_result = save_editor_config(
            config_path,
            config,
            expected_revision=base_revision,
        )
    except ConfigRevisionConflictError as exc:
        raise ConfigApplyError(str(exc), "revision_conflict", 409) from exc
    except ConfigValidationError as exc:
        raise ConfigApplyError(
            "Configuration validation failed",
            "validation_failed",
            422,
            diagnostics={"errors": exc.errors, "warnings": exc.warnings},
        ) from exc

    try:
        runtime_controller.reload()
    except Exception as exc:
        restore_editor_config(
            config_path,
            save_result["previous_raw_yaml"],
            save_result["previous_exists"],
        )
        rollback_error = None
        try:
            runtime_controller.reload()
        except Exception as rollback_exc:  # pragma: no cover
            rollback_error = str(rollback_exc)

        raise ConfigApplyError(
            "Bridge reload failed",
            "reload_failed",
            500,
            details=str(exc),
            rollback_error=rollback_error,
        ) from exc

    return {
        "saved": True,
        "applied": True,
        "config": save_result["config"],
        "revision": save_result["revision"],
        "diagnostics": save_result["diagnostics"],
        "runtime": runtime_controller.get_status(),
    }
