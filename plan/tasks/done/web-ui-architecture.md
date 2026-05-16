# Task: web-ui-architecture

## Title

Define add-on web UI architecture

## Objective

Choose the Home Assistant add-on web delivery model for the Scheiber web interface, including ingress exposure, backend process layout, shared configuration ownership, and how the UI coexists with the existing CAN-to-MQTT bridge.

## Proposed direction

- Add a small Python web application under `scheiber/src/`.
- Serve the UI from the add-on itself through Home Assistant ingress.
- Keep UI concerns out of `scheiber` hardware code and out of MQTT entity classes.
- Let the web layer own:
  - config CRUD and validation,
  - discovery session APIs,
  - bridge lifecycle actions,
  - static asset delivery.

## Decisions to make

1. whether the web app and bridge run in one process or under a lightweight supervisor,
2. how the web app gets live status and discovery events,
3. whether bridge reload is in-process or by controlled restart,
4. how ingress/auth expectations from Home Assistant shape the HTTP layer.

## Constraints from current codebase

- `run.sh` currently starts only `can-mqtt-bridge`.
- `create_scheiber_system()` loads config and state at startup.
- `ScheiberCanBus` currently supports one message callback plus stats observers.
- `scheiber/config.yaml` does not yet expose a web UI.

## Deliverables

- architecture decision for web server placement,
- backend package location and module boundaries,
- event flow between bridge, CAN runtime, discovery, and UI,
- config ownership and reload strategy.
