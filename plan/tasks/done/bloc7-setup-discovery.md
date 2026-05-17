# Task: bloc7-setup-discovery

## Title

Add setup and discovery workflows for Bloc7 reverse engineering

## Depends on

- `bloc7-runtime-config`

## Objective

Expose enough inspection and setup support to turn live MCP/CAN observations into usable Bloc7 sensor configuration, while keeping the operator in control of matcher selection because the segment placement and arbitration-ID extraction rules are still unknown.

## Discovery basis

- Recent live captures show a strong normalized tank-value family under `0x020405xx`, including:
  - `0x02040582` carrying `fuel/0` and `freshWater/0`,
  - `0x02040583` carrying `fuel/1` and `freshWater/1`,
  - `0x0204058A` carrying two black-water values,
  - `0x0204058B` and `0x02060583` appearing to carry the remaining black-water values.
- `0x02040Bxx` looks more like raw sender/resistance-style data than the normalized percentages published by SignalK.
- The low-byte patterns are useful evidence, but there is not yet enough information to derive a safe general Bloc7 segment/bus extraction rule.

## Needed changes

- extend the setup/discovery layer so Bloc7 candidates can be inspected alongside Bloc9 candidates without pretending the identity model is complete,
- surface candidate arbitration IDs, payload bytes, and recent history clearly enough that an operator can choose which frame family to bind,
- allow the setup flow to create or edit Bloc7 sensors from observed CAN candidates by entering:
  - sensor name/entity id,
  - semantic type such as voltage or level,
  - explicit matcher,
  - byte position, bit length, endianness, and scale,
- keep discovery output honest about confidence levels, distinguishing:
  - observed candidate families,
  - operator-confirmed mappings,
  - and unverified heuristics,
- make the MCP/web UI workflow preserve raw evidence needed for future automation of Bloc7 identity extraction.

## Constraints

- Do not auto-generate Bloc7 device IDs from low-byte patterns unless the implementation keeps that behavior explicitly provisional and optional.
- Favor manual confirmation over silent auto-binding.
- Reuse the existing shared CAN inspector rather than creating a second capture path.
- Keep discovery behavior read-only and safe on real hardware.

## Deliverables

- setup/MCP support for inspecting and binding Bloc7 candidate frames,
- an editor/discovery model that can express provisional Bloc7 mappings without segment assumptions,
- a clear operator workflow for turning live CAN evidence into saved Bloc7 config.
