# Task: web-ui-availability

## Title

Make web UI availability configurable and safe by default

## Objective

Refactor the add-on startup and web runtime configuration so the Scheiber setup UI can be disabled entirely when not needed, while still supporting ingress-only access by default and explicit opt-in network exposure during setup.

## Needed changes

- add an add-on option that controls whether the web UI process starts at all,
- add an add-on option that controls whether the web UI binds to loopback only or to all network interfaces,
- wire that option through `scheiber/config.yaml`, `scheiber/run.sh`, and the `scheiber_web` CLI/runtime settings,
- keep Home Assistant ingress working when the UI is restricted to loopback,
- update tests around web runtime startup/configuration so the bind choice is covered,
- document the security behavior and the new option in user-facing release notes or docs.

## Constraints

- preserve the current ingress-based setup workflow,
- do not change CAN, MQTT, or read-only behavior outside the web server bind configuration,
- prefer a secure default because the add-on runs in `host_network` mode,
- keep the configuration surface clear enough for Home Assistant add-on users.

## Deliverables

- configurable web UI startup and bind behavior in the add-on runtime,
- tests proving the selected bind target flows through startup correctly,
- release/documentation updates explaining how to expose the UI intentionally.
