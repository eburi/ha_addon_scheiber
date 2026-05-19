# Task: bloc7-runtime-grouping

## Title

Group Bloc7 sensors by decoded route while preserving manual matchers

## Depends on

- `scheiber-address-family-model`

## Objective

Improve Bloc7 runtime and configuration handling so sensors can be grouped under documented Bloc7 routes like `0_2`, `0_3`, `1_2`, and `1_3`, while remaining backward compatible with the existing matcher-based Bloc7 configuration introduced before the route encoding was understood.

## Needed changes

- allow Bloc7 devices to use nonzero `segment_id` in editor/runtime configuration,
- keep existing v6.2.0-era and current manual matcher-based Bloc7 configs valid,
- migrate or normalize saved Bloc7 devices that used synthetic `bus_id` values for individual message cards without losing entity IDs or matchers,
- group related Bloc7 message families for one route:
  - normalized tank frames such as `0x02040582`,
  - raw/resistance-like frames such as `0x02060582`,
  - status/heartbeat-like frames such as `0x00000582`,
- keep sensor definitions explicit enough that byte extraction remains operator-confirmed,
- add support for Bloc7 battery-oriented sensors:
  - voltage,
  - current,
  - state of charge,
  - optional raw/debug fields when scaling is still provisional.

## Constraints

- Field deployments before this work used Bloc9 only, so Bloc9 configuration and behavior must remain unchanged.
- Do not require existing Bloc7 manual matcher configs to be rewritten before startup.
- Preserve entity IDs and persistence keys across normalization.
- Keep `read_only` safety behavior unchanged.
- Do not infer S/Y versus M/Y applicability at runtime unless the operator selects or confirms a documentation profile.

## Deliverables

- route-aware Bloc7 config model that still accepts manual matchers,
- compatibility path for existing Bloc7 message-card configs,
- tests covering legacy config load/save, normalized route grouping, and persisted state compatibility,
- operator-facing notes for the Lagoon S/Y Bloc7 X44/X43/X220/X234 mappings.
