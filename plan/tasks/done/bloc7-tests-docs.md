# Task: bloc7-tests-docs

## Title

Cover Bloc7 integration with tests, fixtures, and operator documentation

## Depends on

- `bloc7-runtime-config`
- `bloc7-setup-discovery`

## Objective

Lock down the Bloc7 integration with repository-native tests and documentation so future reverse engineering can refine the matching rules without regressing the manual-first configuration path.

## Needed changes

- add unit tests for Bloc7 config validation, runtime creation, persisted-state restore/store, and MQTT sensor publication,
- add tests for any new discovery/setup helpers using captured CAN examples that reflect the currently observed `0x020405xx`, `0x020605xx`, and `0x02040Bxx` families,
- document the supported Bloc7 configuration format in repository docs and example config files,
- document the current reverse-engineering status explicitly:
  - which frame families are strongly supported,
  - which mappings remain provisional,
  - and why segment-aware ID extraction is intentionally not automated yet,
- provide an operator-facing workflow for correlating SignalK values with MCP CAN captures and encoding the result into config.

## Constraints

- Use the repository's existing test stack only.
- Keep documentation clear about uncertainty; do not present provisional mappings as settled protocol rules.
- Prefer small captured fixtures over brittle broad integration tests that require live hardware.

## Deliverables

- automated coverage for the Bloc7 config and bridge paths,
- fixtures and tests for current reverse-engineered Bloc7 message families,
- documentation and example configuration sufficient to deploy Bloc7 sensors manually.
