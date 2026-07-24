# Air Switch Saved Log Findings - 2026-07-12

Source: `/data/interactions_log.jsonl` from `buttercup.local`, analyzed with `scheiber/src/tools/analyze_air_switch_log.py`.

## Terminology

- `0x04001A80`, `0x04001A82`, `0x04001A83` are CAN arbitration IDs.
- `52AB81` and `52A8DC` are 3-byte wireless Air Switch transmitter identities inside the payload, not arbitration IDs.
- Example: `0x04001A80  01 52 AB 81 82` means CAN ID `0x04001A80`, payload leader `01`, transmitter identity `52AB81`, status `0x82` (`pressed`, button index `2`).

## Current Mapping Evidence

| Location | Unit type | Identity | Function | Button index |
|---|---:|---|---|---:|
| bow salon | 4-function | `52AB81` | Top Left | `2` |
| bow salon | 4-function | `52AB81` | Bottom Left | `1` |
| bow salon | 4-function | `52AB81` | Top Right | `4` |
| bow salon | 4-function | `52AB81` | Bottom Right | mostly `3`, also repeated `5` |
| crew cabin | 2-function | `52A8DC` | Top | mostly `2`, also a few `1` |
| crew cabin | 2-function | `52A8DC` | Bottom | `1` |

Likely clean mapping pattern:

- 2-function unit: top = `2`, bottom = `1`.
- 4-function unit: bottom-left = `1`, top-left = `2`, bottom-right = `3`, top-right = `4`.

## Anomalies To Recheck

- Bow salon bottom-right produced repeated `index=5` press/release cycles, not just one stray frame. Re-run this function deliberately to determine whether `5` is real, caused by combined/mis-press behavior, or an artifact of receiver/reporting behavior.
- Crew cabin top produced a few `index=1` frames while mostly producing `index=2`. This is probably one accidental bottom-button press during the top-button step, but should be verified if recaptured.

## Receiver-Path Observation

- Bow salon identity `52AB81` appeared under CAN IDs `0x04001A80`, `0x04001A82`, and `0x04001A83`.
- Crew cabin identity `52A8DC` appeared mostly under `0x04001A80` and `0x04001A82`; `0x04001A83` appeared only once.
- This supports, but does not prove, that the low-byte variants may represent receiver paths, retransmission paths, or duplicate-report handling. The transmitter identity remains the payload identity, not the arbitration ID.

## Reactions Seen

- Bow salon Top Left: Bloc9 `#3` outputs `s5/s6`.
- Bow salon Bottom Left: Bloc9 `#10_2` outputs `s1/s2` and `s3/s4`.
- Bow salon Top Right: Bloc9 `#1` outputs `s3/s4`.
- Bow salon Bottom Right: mainly Bloc9 `#1` outputs `s3/s4`, with one Bloc9 `#5_3` output `s3/s4` reaction.
- Crew cabin Top/Bottom: Bloc9 `#3_2`, outputs `s3/s4` and `s1/s2`.
