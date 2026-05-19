# Task: setup-ui-protocol-discovery

## Title

Make setup discovery protocol-aware across Scheiber device families

## Depends on

- `scheiber-address-family-model`
- `bloc7-runtime-grouping`
- `sourceselector-ac-monitoring`

## Objective

Rework setup web UI and MCP discovery output so operators see candidates grouped by decoded route and device family, with enough evidence to promote frames into configuration safely.

## Needed changes

- display decoded route labels consistently, for example `0_2`, `1_3`, or local `3`,
- group candidates by route plus family instead of by one arbitration ID per card,
- show family-specific evidence:
  - Bloc9 state/heartbeat/control evidence,
  - Bloc7 status, normalized values, raw sender values, and documentation input hints,
  - SourceSelector voltage/frequency slots and inactive `0V/0Hz` slots,
  - battery/IBS voltage/current/state-of-charge candidates,
- show confidence and uncertainty explicitly when classification is based on live capture rather than documentation,
- allow users to promote grouped candidates into config while preserving editable names, entity IDs, scales, units, and byte extraction,
- add UI warnings for high-power AC SourceSelector measurements and keep them read-only,
- keep the MCP `detect_bloc7_candidates` compatibility path available while adding a broader protocol-aware candidate resource/tool.

## Constraints

- Stay backward compatible with version 6.2.0 configuration and field deployments that only used Bloc9.
- Do not remove current Bloc9 discovery workflows; adapt them onto the shared route/family model.
- Avoid automatic reassignment of existing entity names based only on live values.
- Do not hide raw arbitration IDs; setup and reverse engineering still need them.

## Deliverables

- grouped protocol-aware candidate model for web UI and MCP,
- updated Bloc7 setup cards based on real route grouping,
- SourceSelector and battery candidate cards,
- compatibility tests for existing MCP/web responses where callers expect Bloc7 candidate data.
