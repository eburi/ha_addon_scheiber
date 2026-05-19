# Task: config-compatibility-v620

## Title

Preserve v6.2.0 configuration compatibility while adding new families

## Depends on

- `bloc7-runtime-grouping`
- `sourceselector-ac-monitoring`
- `setup-ui-protocol-discovery`

## Objective

Add compatibility coverage and migration guardrails so route-aware Bloc7 grouping, SourceSelector sensors, and protocol-aware discovery do not break v6.2.0-era configurations or existing Bloc9-only deployments.

## Needed changes

- collect or reconstruct representative v6.2.0 configuration fixtures,
- verify Bloc9-only configs load, validate, save, and publish identically where behavior is not intentionally changed,
- verify existing matcher-based Bloc7 configs remain valid and preserve entity IDs,
- add normalization tests for old synthetic Bloc7 message devices into route-aware groupings when the operator chooses to save through the new UI,
- ensure unknown future device families remain ignored or surfaced as candidates instead of causing validation failures,
- document migration behavior and any non-lossy rewrite that happens on save.

## Constraints

- Do not require a migration for users who only run existing Bloc9 devices.
- Do not silently rename entities or change MQTT topics for existing configured devices.
- Any config rewrite must be deterministic and reviewable in the setup UI.
- Version/changelog updates belong to implementation tasks, not this planning task.

## Deliverables

- fixture coverage for v6.2.0-compatible Bloc9 and current Bloc7 configs,
- config validation and save/load tests for new device families,
- migration notes for operator documentation,
- explicit acceptance criteria for backward compatibility before release.
