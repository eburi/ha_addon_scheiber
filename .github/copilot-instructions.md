# GitHub Copilot / AI Agent Instructions — scheiber

This file contains targeted, actionable guidance for an AI coding agent working in this repository.
Keep updates short and concrete; prefer small, focused edits using the repo's existing conventions.

Core purpose
- This repository provides Python utilities that interact with scheiber devices over a SocketCAN bus.
- Key runtime integration points: `python-can` (socketcan backend), the `scheiber/tools` helpers, and sample CAN dumps in `scheiber/tools/data/`.

**Working directory assumption**
- All Python code in `scheiber/tools/` is deployed to run with `scheiber/tools/` as the working directory.
- Scripts should use relative imports (e.g., `from canlistener import PATTERNS`) when importing sibling modules in tools/.
- Data files are expected at `./data/` (relative to tools/).
- When testing locally, run scripts from the tools folder or adjust sys.path accordingly.

Important files and their roles
- `scheiber/scheiber.py`: original interactive CAN listener and utilities (high-level). Use for reference only.
- `scheiber/tools/scheiber.py`: low-level utility functions used by tools (e.g. `send_burst`, `bloc9_switch`, `test_switch`).
- `scheiber/tools/canlistener.py`: active CAN listener that decodes Bloc9 messages (moved here from scheiber.py).
- `scheiber/tools/light.py`: `push_light_button()` helper (sends a two-packet press/release sequence).
- `scheiber/tools/data/`: sample dump files used for analysis and inference of message formats.
- `scheiber/tools/can_names.csv`: human-readable mapping of known arbitration id prefixes and device comments.

Key patterns and protocols (must be respected)
- Bloc9 CAN-ID construction (used when sending commands):
  - Build a byte by: `(bloc9_id << 3) | 0x80` (set MSB and shift left 3)
  - OR that byte into the low byte of `0x02360600` to make the full arbitration id.
    Example: `bloc9_id = 10` -> lowest byte = `0xD0`, full id `0x023606D0`.
- Command payload for switching: 4 bytes
  - Byte 0: `switch_nr` (numeric)
  - Byte 1: `0x01` for ON or `0x00` for OFF
  - Bytes 2..3: `0x00, 0x00`
- Known status prefixes (upper 24 bits):
  - `0x00000600` — Bloc9 low-priority status
  - `0x02160600` — S1 & S2 change messages
  - `0x02180600` — S3 & S4 change messages
  - `0x021A0600` — S5 & S6 change messages

Agent coding rules for this repo
- Follow existing style (snake_case functions, concise helpers in `scheiber/tools`).
- When changing code that opens `can.interface.Bus`, always open in a try/finally and call `bus.shutdown()` in `finally`.
- Use `apply_patch` for edits (small focused patches). Don't reformat whole files.
- Avoid touching hardware-specific code unless the change is clearly safer (e.g., better error handling or clear abstractions). When in doubt, add a small wrapper or feature-flag.

Common developer workflows (how to run things locally)
- Install runtime deps (if not present): `pip install python-can paho-mqtt`
- **All scripts run from the `scheiber/tools/` folder:**
  - Test switch sequence: `cd scheiber/tools && python scheiber.py 3 7`
  - CAN listener: `cd scheiber/tools && python canlistener.py can1`
  - Light button: `cd scheiber/tools && python light.py can1`
  - MQTT bridge: `cd scheiber/tools && python mqtt_bridge.py --debug`

What agents should do first (on a new task)
1. Read `scheiber/tools/can_names.csv` and `scheiber/tools/data/` to understand message examples.
2. Prefer changes in `scheiber/tools/*` — this folder contains the small, testable utilities.
3. When adding decoding rules, update `canlistener.py` PATTERNS and include a short example mapping and a unit-like small runner.

Testing and safety
- There are no automated tests. Add small runnable scripts that can be executed without hardware by mocking `can.interface.Bus` or by guarding with `if __name__ == '__main__'`.
- Keep hardware-side changes minimal. Prefer adding a `dry_run` boolean parameter to functions that would otherwise send onto a real CAN bus.

If you need clarification
- Ask for a small concrete artifact (e.g., a single representative dump line) before changing decoding heuristics.

End of instructions — request feedback if anything here is unclear.
