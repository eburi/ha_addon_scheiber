# Task: test-strategy

## Title

Define validation strategy

## Depends on

- `config-editor-api`
- `discovery-pipeline`
- `runtime-integration`

## Objective

Plan tests for config parsing, API validation, discovery pattern matching, UI integration seams, and add-on startup behavior so the new web interface can be added without regressing the current bridge.

## Coverage areas

- config load/validate/save behavior,
- duplicate `bus_id` and `entity_id` rejection,
- invalid Bloc9 output names rejection,
- discovery classification from known arbitration IDs,
- discovery candidate aggregation,
- bridge lifecycle behavior during apply/reload,
- web/backend contract tests,
- startup and shutdown behavior with the web UI enabled.

## Test shape

- keep using the existing Python test setup,
- prefer unit tests around config and discovery services,
- add integration-style tests where web actions affect runtime lifecycle,
- avoid hardware dependency by mocking CAN and MQTT boundaries.

## Deliverables

- test matrix for backend, discovery, and runtime behavior,
- fixtures/mocks needed for CAN and MQTT interactions,
- minimal integration coverage for config apply and recovery paths.
