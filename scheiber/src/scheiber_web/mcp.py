"""Minimal MCP server surface for Scheiber configuration and CAN inspection."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from scheiber.config import (
    ConfigValidationError,
    load_editor_state,
    validate_editor_config,
)

from .bloc7_candidates import (
    build_bloc7_candidate_snapshot,
    build_protocol_candidate_snapshot,
)
from .config_ops import ConfigApplyError, apply_editor_config

JSONRPC_VERSION = "2.0"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2024-11-05")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]
SERVER_INFO = {"name": "scheiber-mcp", "version": "6.7.0"}


class MCPRequestError(ValueError):
    """Raised for JSON-RPC level request errors."""

    def __init__(
        self,
        code: int,
        message: str,
        *,
        data: Optional[Dict[str, Any]] = None,
        request_id: Any = None,
        http_status: int = 200,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.data = data
        self.request_id = request_id
        self.http_status = http_status

    def to_response(self) -> Dict[str, Any]:
        error: Dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.data is not None:
            error["data"] = self.data
        return {"jsonrpc": JSONRPC_VERSION, "id": self.request_id, "error": error}


class ScheiberMCPServer:
    """Serve a compact MCP interface on top of the shared runtime."""

    def __init__(self, settings, runtime_controller, inspector) -> None:
        self.settings = settings
        self.runtime_controller = runtime_controller
        self.inspector = inspector

    def handle_request(self, payload: Any) -> Optional[Tuple[Dict[str, Any], int]]:
        """Handle one JSON-RPC request object."""
        if not isinstance(payload, dict):
            raise MCPRequestError(-32600, "Request must be a JSON object")
        if (
            "id" in payload
            and "jsonrpc" in payload
            and payload["jsonrpc"] != JSONRPC_VERSION
        ):
            raise MCPRequestError(
                -32600,
                "Only JSON-RPC 2.0 requests are supported",
                request_id=payload.get("id"),
            )

        method = payload.get("method")
        request_id = payload.get("id")
        params = payload.get("params", {})
        if not isinstance(method, str) or not method:
            raise MCPRequestError(
                -32600, "Request method is required", request_id=request_id
            )
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise MCPRequestError(
                -32602,
                "Request params must be an object",
                request_id=request_id,
            )

        result = self._dispatch(method, params, request_id)
        if request_id is None:
            return None
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}, 200

    def _dispatch(
        self, method: str, params: Dict[str, Any], request_id: Any
    ) -> Dict[str, Any]:
        if method == "initialize":
            return self._initialize(params)
        if method == "notifications/initialized":
            return {}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self._tool_definitions()}
        if method == "tools/call":
            return self._call_tool(params)
        if method == "resources/list":
            return {"resources": self._resource_definitions()}
        if method == "resources/read":
            return self._read_resource(params, request_id)

        raise MCPRequestError(
            -32601, f"Method not found: {method}", request_id=request_id
        )

    def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        requested_version = params.get("protocolVersion")
        if (
            isinstance(requested_version, str)
            and requested_version in SUPPORTED_PROTOCOL_VERSIONS
        ):
            protocol_version = requested_version
        else:
            protocol_version = LATEST_PROTOCOL_VERSION

        return {
            "protocolVersion": protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
            },
            "serverInfo": SERVER_INFO,
            "instructions": (
                "Use config resources/tools to read or update scheiber-config.yaml. "
                "Use CAN inspection tools/resources to capture live bus traffic for "
                "reverse engineering. Config writes are validated, atomic, and reload "
                "the running bridge."
            ),
        }

    def _tool_definitions(self) -> list[Dict[str, Any]]:
        return [
            {
                "name": "get_config",
                "description": (
                    "Read the current Scheiber editor configuration, diagnostics, and "
                    "revision metadata."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "include_raw_yaml": {"type": "boolean", "default": True}
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "validate_config",
                "description": (
                    "Validate a proposed editor configuration object without saving it."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"config": {"type": "object"}},
                    "required": ["config"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "save_config",
                "description": (
                    "Persist a validated editor configuration and reload the running "
                    "bridge."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "config": {"type": "object"},
                        "base_revision": {"type": ["string", "null"]},
                    },
                    "required": ["config"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_runtime_status",
                "description": "Read the current shared runtime status.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "name": "read_can_snapshot",
                "description": (
                    "Return the current CAN inspection snapshot and optionally start "
                    "capture if it is not already running."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "start_if_needed": {"type": "boolean", "default": True}
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "read_can_detail",
                "description": (
                    "Return detailed history and bit diffs for one arbitration ID."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "arbitration_id": {"type": ["string", "integer"]},
                        "start_if_needed": {"type": "boolean", "default": True},
                    },
                    "required": ["arbitration_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "stop_can_inspection",
                "description": "Stop CAN inspection capture and return the final snapshot.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "name": "detect_bloc7_candidates",
                "description": (
                    "Return likely Bloc7 sensor candidates inferred from the shared CAN inspector."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "start_if_needed": {"type": "boolean", "default": True}
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "detect_protocol_candidates",
                "description": (
                    "Return protocol-aware Scheiber candidates grouped by route and family."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "start_if_needed": {"type": "boolean", "default": True}
                    },
                    "additionalProperties": False,
                },
            },
        ]

    def _resource_definitions(self) -> list[Dict[str, Any]]:
        return [
            {
                "uri": "scheiber://config/state",
                "name": "Scheiber config state",
                "description": "Editor config, revision metadata, and validation diagnostics.",
                "mimeType": "application/json",
            },
            {
                "uri": "scheiber://config/raw",
                "name": "Scheiber raw config YAML",
                "description": "The raw scheiber-config.yaml contents.",
                "mimeType": "text/yaml",
            },
            {
                "uri": "scheiber://runtime/status",
                "name": "Scheiber runtime status",
                "description": "The live shared runtime status and active management flags.",
                "mimeType": "application/json",
            },
            {
                "uri": "scheiber://can/snapshot",
                "name": "Scheiber CAN snapshot",
                "description": "The current CAN inspector snapshot without starting capture.",
                "mimeType": "application/json",
            },
            {
                "uri": "scheiber://can/bloc7-candidates",
                "name": "Scheiber Bloc7 candidates",
                "description": "Likely Bloc7 sensor candidates inferred from recent CAN traffic.",
                "mimeType": "application/json",
            },
            {
                "uri": "scheiber://can/protocol-candidates",
                "name": "Scheiber protocol candidates",
                "description": "Protocol-aware CAN candidates grouped by Scheiber route and family.",
                "mimeType": "application/json",
            },
        ]

    def _read_resource(self, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise MCPRequestError(
                -32602,
                "resources/read requires a non-empty uri",
                request_id=request_id,
            )

        if uri == "scheiber://config/state":
            state = load_editor_state(self.settings.config_path)
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": self._as_json_text(state),
                    }
                ]
            }
        if uri == "scheiber://config/raw":
            state = load_editor_state(self.settings.config_path)
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "text/yaml",
                        "text": state.get("raw_yaml", ""),
                    }
                ]
            }
        if uri == "scheiber://runtime/status":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": self._as_json_text(
                            self.runtime_controller.get_status()
                        ),
                    }
                ]
            }
        if uri == "scheiber://can/snapshot":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": self._as_json_text(self.inspector.snapshot()),
                    }
                ]
            }
        if uri == "scheiber://can/bloc7-candidates":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": self._as_json_text(
                            build_bloc7_candidate_snapshot(
                                self.inspector, start_if_needed=False
                            )
                        ),
                    }
                ]
            }
        if uri == "scheiber://can/protocol-candidates":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": self._as_json_text(
                            build_protocol_candidate_snapshot(
                                self.inspector, start_if_needed=False
                            )
                        ),
                    }
                ]
            }

        raise MCPRequestError(
            -32602,
            f"Unknown resource URI: {uri}",
            request_id=request_id,
        )

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name:
            raise MCPRequestError(-32602, "tools/call requires a non-empty tool name")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise MCPRequestError(-32602, "tools/call arguments must be an object")

        try:
            result = self._execute_tool(name, arguments)
        except ConfigApplyError as exc:
            return self._tool_error_result(exc.to_response())
        except ConfigValidationError as exc:
            return self._tool_error_result(
                {
                    "error": "Configuration validation failed",
                    "code": "validation_failed",
                    "diagnostics": {"errors": exc.errors, "warnings": exc.warnings},
                }
            )
        except RuntimeError as exc:
            return self._tool_error_result({"error": str(exc), "code": "runtime_error"})
        except ValueError as exc:
            return self._tool_error_result(
                {"error": str(exc), "code": "invalid_request"}
            )

        return {
            "content": [{"type": "text", "text": self._as_json_text(result)}],
            "structuredContent": result,
            "isError": False,
        }

    def _execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "get_config":
            state = load_editor_state(self.settings.config_path)
            if not arguments.get("include_raw_yaml", True):
                state = dict(state)
                state.pop("raw_yaml", None)
            return state

        if name == "validate_config":
            config = self._require_argument(arguments, "config")
            normalized_config, warnings = validate_editor_config(config)
            return {
                "valid": True,
                "config": normalized_config,
                "diagnostics": {"errors": [], "warnings": warnings},
            }

        if name == "save_config":
            config = self._require_argument(arguments, "config")
            return apply_editor_config(
                self.settings.config_path,
                self.runtime_controller,
                config,
                base_revision=arguments.get("base_revision"),
            )

        if name == "get_runtime_status":
            return self.runtime_controller.get_status()

        if name == "read_can_snapshot":
            start_if_needed = arguments.get("start_if_needed", True)
            snapshot = self.inspector.snapshot()
            if start_if_needed and snapshot["status"] != "running":
                snapshot = self.inspector.start()
            return snapshot

        if name == "read_can_detail":
            start_if_needed = arguments.get("start_if_needed", True)
            snapshot = self.inspector.snapshot()
            if start_if_needed and snapshot["status"] != "running":
                self.inspector.start()

            arb_id = self._parse_arbitration_id(
                self._require_argument(arguments, "arbitration_id")
            )
            detail = self.inspector.detail(arb_id)
            if detail is None:
                raise ValueError(
                    f"No CAN history available yet for arbitration ID 0x{arb_id:08X}"
                )
            return detail

        if name == "stop_can_inspection":
            return self.inspector.stop()

        if name == "detect_bloc7_candidates":
            return build_bloc7_candidate_snapshot(
                self.inspector,
                start_if_needed=arguments.get("start_if_needed", True),
            )

        if name == "detect_protocol_candidates":
            return build_protocol_candidate_snapshot(
                self.inspector,
                start_if_needed=arguments.get("start_if_needed", True),
            )

        raise MCPRequestError(-32602, f"Unknown tool: {name}")

    def _tool_error_result(self, error: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": self._as_json_text(error)}],
            "structuredContent": error,
            "isError": True,
        }

    @staticmethod
    def _require_argument(arguments: Dict[str, Any], key: str) -> Any:
        if key not in arguments:
            raise ValueError(f"Missing required argument: {key}")
        return arguments[key]

    @staticmethod
    def _parse_arbitration_id(value: Any) -> int:
        if isinstance(value, int):
            arb_id = value
        elif isinstance(value, str):
            text = value.strip().lower()
            arb_id = int(text, 16) if text.startswith("0x") else int(text, 0)
        else:
            raise ValueError("arbitration_id must be an integer or hex string")

        if arb_id < 0:
            raise ValueError("arbitration_id must be non-negative")
        return arb_id

    @staticmethod
    def _as_json_text(payload: Dict[str, Any]) -> str:
        return json.dumps(payload, indent=2, sort_keys=True)
