# Task: scheiber-address-family-model

## Title

Model shared Scheiber address bytes and message families

## Objective

Introduce a protocol model that decodes the shared Scheiber low-byte address format while keeping message-family classification explicit, so Bloc9, Bloc7, SourceSelector, and battery/IBS observations can be grouped without mislabeling unrelated frames as Bloc9.

## Discovery basis

- Bloc9 already uses `0x80 | (bus_id << 3) | segment_id` for the arbitration-ID low byte.
- Documented Bloc7 routes match the same low-byte address format:
  - X44 `BLOC 7@0_2` -> low byte `0x82`
  - X43 `BLOC 7@0_3` -> low byte `0x83`
  - X220 `BLOC 7@1_2` -> low byte `0x8A`
  - X234 `BLOC 7@1_3` -> low byte `0x8B`
- Bloc7 troubleshooting documentation says Bloc7 code is physically selected by input 20, with no wire = code `0` and grounded wire = code `1`.
- Bloc9 documentation says Bloc9 modules are differentiated by a microswitch-allocated network number.
- Live captures show family prefixes matter:
  - `0x000005xx` aligns with Bloc7 status/heartbeat-like frames,
  - `0x000006xx` aligns with Bloc9 status/heartbeat-like frames but must not be classified as Bloc9 solely by prefix when no Bloc9 state/control evidence exists,
  - `0x00000Bxx` and `0x02040Bxx` align with SourceSelector observations,
  - `0x020405xx` and `0x020605xx` align with Bloc7 level/raw sender observations.

## Needed changes

- extract shared route helpers for decoding and formatting Scheiber low-byte route addresses,
- replace Bloc9-only naming in generic address decode paths with shared route terminology,
- add explicit message-family classification that combines:
  - arbitration-ID prefix,
  - decoded route,
  - payload shape,
  - observed companion frames for the same route,
- prevent the inspector from labeling every `0x000006xx` frame as a verified Bloc9 heartbeat unless the route is configured as Bloc9 or has Bloc9 state/control evidence,
- represent unknown or ambiguous families as provisional evidence instead of forcing them into Bloc9 or Bloc7.

## Constraints

- Preserve existing Bloc9 local and segment-aware decode behavior.
- Do not change CAN command behavior in this task.
- Keep route identity distinct from device type; the same route bits are only meaningful together with a message family.
- Do not assume full arbitration-ID collisions are safe. Treat uniqueness as required for each full arbitration ID, not merely each low-byte route.

## Deliverables

- shared route decoding and formatting helpers,
- family-aware classification model for inspector/MCP output,
- updated tests for Bloc9, Bloc7, SourceSelector, and ambiguous heartbeat/status frames,
- documentation comments that distinguish confirmed protocol facts from live-capture hypotheses.
