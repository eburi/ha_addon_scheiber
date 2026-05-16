# Task: bloc9-segment-routing

## Title

Implement segment-aware Bloc9 routing and setup UI support

## Depends on

- `discovery-pipeline`
- `frontend-workflow`

## Objective

Implement the newly observed multi-segment Bloc9 arbitration ID logic so the runtime can decode remote Bloc9 state updates and expose enough setup UI controls to test whether the same encoding also supports cross-segment control.

## Discovery basis

- Local Bloc9 arbitration IDs use the known low-byte form `0x80 | (bus_id << 3)`.
- Remote Bloc9 `3_2` status updates were observed as:
  - `0x0216069A` for S1/S2
  - `0x0218069A` for S3/S4
  - `0x021A069A` for S5/S6
- The remote low byte `0x9A` matches the local ID-3 value `0x98` plus `0x02`, suggesting the low 3 bits may encode a segment identifier while preserving the existing Bloc9 payload structure.
- Additional duplicated frames such as `0x04021809` look like bridge or panel-layer reporting and should be treated as supporting evidence, not the primary control protocol, until control has been verified.

## Needed changes

- extend Bloc9 arbitration decoding to preserve both local `bus_id` and possible segment suffix bits,
- keep existing same-segment matching and command generation working unchanged,
- add an explicit segment-aware device identity model for discovery and setup flows,
- update the setup web UI and inspect tooling to display segment-aware candidates and raw IDs clearly,
- add a way in the setup UI to send a test command against a selected segment-aware Bloc9 target,
- make the result observable so testing can distinguish:
  - reporting only,
  - reporting plus control,
  - or unsupported control attempts.

## Constraints

- Do not break existing single-segment Bloc9 setups.
- Keep native Bloc9 payload decoding unchanged unless evidence shows otherwise.
- Avoid assuming the bridge accepts cross-segment control until a real test proves it.
- Treat forwarded status and forwarded control as separate capabilities.

## Deliverables

- segment-aware arbitration ID decode/encode rules in the runtime,
- updated discovery output model for local vs remote/segmented candidates,
- setup web UI changes for inspecting and testing segment-aware targets,
- a documented test path for verifying whether cross-segment control works or only reporting does.
