# Task: mcp-addon-activation

## Title

Make MCP activation opt-in in the add-on configuration

## Depends on

- `mcp-server-runtime`

## Objective

Wire the new MCP capability through the Home Assistant add-on configuration and startup flow so operators can enable it only when needed, while receiving a clear warning that it should be used temporarily for setup and reverse-engineering work.

## Needed changes

- add an add-on option that enables the MCP server,
- ensure startup launches the shared management runtime whenever MCP is enabled,
- emit a clear startup warning when MCP is active,
- document the new option and temporary-use warning in the add-on metadata and repository docs,
- update versioning and changelog for the new user-facing capability.

## Constraints

- preserve the current non-MCP bridge-only startup path when neither the web UI nor MCP are enabled,
- avoid adding a separate always-on listener or extra transport that would expand the hardware control surface unnecessarily,
- keep the warning specific that MCP exposes configuration editing and live CAN inspection and should be disabled after setup or reverse engineering is complete.

## Deliverables

- updated add-on options/startup wiring,
- visible warning text in configuration-facing documentation/metadata and logs,
- version and changelog entries for the MCP feature.
