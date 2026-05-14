# Task: discovery-pipeline

## Title

Design Bloc9 discovery pipeline

## Depends on

- `web-ui-architecture`

## Objective

Plan the live discovery flow that monitors CAN traffic for known Bloc9 arbitration ID patterns, extracts candidate bus IDs and output groups, and exposes discovery results to the web interface without interfering with the running bridge.

## Detection basis

Use known Bloc9 state update prefixes:

- `0x02160600` for S1/S2
- `0x02180600` for S3/S4
- `0x021A0600` for S5/S6

Use `0x00000600` heartbeats only as supporting evidence, not as authoritative state.

## Discovery model

Track candidates with:

- detected `bus_id`,
- last seen timestamp,
- observed output groups,
- sample arbitration IDs,
- sample decoded brightness/state values,
- confidence notes based on repeated observation.

## Integration direction

- Keep discovery read-only.
- Reuse the shared CAN runtime if possible.
- Add raw message fan-out or observer hooks rather than a separate protocol implementation.
- Expose discovery results to the UI via polling or push updates.

## Deliverables

- discovery session lifecycle,
- arbitration ID decoding rules,
- in-memory result model,
- API shape for starting, stopping, and reading discovery results.
