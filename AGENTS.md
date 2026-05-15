# Agent instructions

These instructions apply to all agents working in this repository.

## Project overview

This repository is a Home Assistant add-on that bridges Scheiber CAN bus devices to Home Assistant through MQTT. Runtime code is Python and is packaged under `scheiber/` for the add-on container.

Key areas:

- `scheiber/src/scheiber/`: client-agnostic Scheiber CAN/device layer.
- `scheiber/src/can_mqtt_bridge/`: MQTT and Home Assistant Discovery bridge layer.
- `scheiber/src/tools/`: CAN debugging and analysis tools.
- `scheiber/src/migrate/`: startup migrations run by the add-on.
- `scheiber/config.yaml`: Home Assistant add-on manifest and user options.
- `scheiber/run.sh`: add-on startup script, CAN interface setup, migrations, and bridge launch.
- `scheiber-config.yaml`: example entity/device configuration.
- `plan/`: durable project planning notes and implementation plans.

## Architecture rules

- Keep CAN protocol and hardware behavior in `scheiber/src/scheiber/`.
- Keep MQTT topics, Home Assistant Discovery, retained state handling, and command parsing in `scheiber/src/can_mqtt_bridge/`.
- Do not make MQTT bridge classes send raw CAN messages directly. Route commands through hardware objects such as `DimmableLight`, `Switch`, and `Bloc9Device`.
- Use the existing observer pattern for state flow from hardware objects to MQTT entities.
- Preserve the configurable `mqtt_topic_prefix`; do not hardcode `homeassistant` in topic construction.
- Treat `read_only` mode as safety-critical: it must prevent sending CAN commands.

## Current CAN/device model

- `ScheiberCanBus` wraps SocketCAN access, tracks bus statistics, and owns `can.interface.Bus` lifecycle.
- `ScheiberSystem` owns configured devices, routes matched CAN messages, logs unknown arbitration IDs once, and persists state.
- `Bloc9Device` models a Bloc9 with six outputs, configured as lights and/or switches.
- `Output` contains Bloc9 matcher and state-decoding logic shared by lights and switches.
- `DimmableLight` adds brightness, fade, flash, and Bloc9 full-brightness translation.
- `Switch` handles binary output state.
- `Matcher` uses `(arbitration_id & mask) == (pattern & mask)`.

Important Bloc9 protocol details:

- Command CAN ID: `0x02360600 | ((device_id << 3) | 0x80)`.
- Command data: `[switch_nr, mode_byte, 0x00, brightness_byte]`.
- Switch numbers are zero-based: S1-S6 map to `0-5`.
- Mode bytes are `0x00` for off, `0x01` for full on, and `0x11` for PWM dimming.
- State change CAN IDs are `0x021606xx` for S1/S2, `0x021806xx` for S3/S4, and `0x021A06xx` for S5/S6.
- State change payloads are 8 bytes. Lower output state is in bytes 0-3; higher output state is in bytes 4-7.
- Heartbeat/status messages are not light/switch state updates.
- Bloc9 reports full-on non-PWM outputs as `state=ON, brightness=0`; MQTT-facing light state must translate that to brightness `255`.

## Configuration and startup

- The v6 configuration format is `devices:`, with each device having `type`, `bus_id`, and optional `lights` and `switches` maps keyed by `s1` through `s6`.
- Entity IDs come from config. Keep state persistence keyed by `entity_id` and maintain migration/backward compatibility when changing state shape.
- `scheiber/run.sh` initializes CAN interfaces, runs migrations from `scheiber/src/migrate/`, activates `/src/.venv`, and starts `can-mqtt-bridge`.
- The add-on options in `scheiber/config.yaml` must stay aligned with CLI arguments in `scheiber/src/can_mqtt_bridge/__main__.py` and startup wiring in `run.sh`.

## Development workflow

- Prefer small, focused changes that preserve layer boundaries.
- Run Python commands inside the repository virtualenv (`scheiber/src/.venv`); activate it first or invoke that interpreter directly instead of the system Python.
- Use the existing Poe tasks from `pyproject.toml` when available:
  - `poe test`
  - `poe lint`
  - `poe check`
- Equivalent direct test command: `python -m pytest scheiber/src/scheiber/tests scheiber/src/can_mqtt_bridge/tests -v`.
- Format Python with Black and isort using the repository settings.
- Do not add new tooling unless the task requires it.
- For docs-only changes, tests are normally unnecessary unless documentation examples or generated artifacts are affected.

## Versioning and changelog

- For user-facing add-on changes, update `scheiber/config.yaml` and `scheiber/CHANGELOG.md`.
- Use semantic versioning:
  - Patch: bug fixes and small compatible tweaks.
  - Minor: backward-compatible features.
  - Major: breaking changes.
- Keep the changelog in Keep a Changelog format with `[Unreleased]` at the top.

## Planning

- Store project planning information in `plan/`.
- Use clear filenames such as `plan/<topic>.md` for durable design notes, implementation plans, and investigation summaries.
- Keep plans concise and update them when implementation decisions change.
- Do not store secrets, credentials, CAN bus captures containing sensitive operational data, or machine-local paths in planning files unless explicitly required and sanitized.

## Safety notes

- CAN commands affect real boat hardware. Be conservative with changes that send messages.
- Prefer mock-based tests for CAN behavior. Do not require physical hardware for automated tests.
- When opening a CAN bus in new code, ensure it is shut down on failure and during normal cleanup.
- Do not swallow errors silently. Log or propagate failures using existing patterns.
