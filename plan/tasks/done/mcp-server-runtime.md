# Task: mcp-server-runtime

## Title

Add an MCP surface on the shared Scheiber management runtime

## Objective

Expose a minimal MCP server from the existing `scheiber_web` process so AI clients can inspect live CAN traffic and read or update the add-on configuration without bypassing the repository's current validation and reload logic.

## Needed changes

- add an MCP request handler that supports the core initialization, tools, and resources calls needed by MCP clients,
- reuse existing config helpers so config reads include revision metadata and config writes stay atomic, validated, and rollback-safe,
- reuse the live CAN inspector so MCP clients can start capture, inspect current arbitration-ID snapshots, and fetch detailed history for specific IDs,
- return structured MCP tool/resource payloads that remain easy for AI clients to consume,
- cover the new endpoint behavior with focused tests.

## Constraints

- keep the MCP implementation inside the existing management/runtime layer instead of creating a second CAN listener,
- do not let config writes bypass validation or runtime reload,
- do not expose CAN command-sending tools through MCP for this feature; the requested scope is config editing plus CAN observation.

## Deliverables

- MCP endpoint implementation in `scheiber_web`,
- MCP tools/resources for config and CAN inspection,
- tests proving initialization, config writes, and CAN inspection responses.
