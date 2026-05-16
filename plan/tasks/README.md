# Scheiber web interface tasks

These task files track follow-up work for the delivered web interface and related setup tooling.

## Goal

Add a Home Assistant add-on web interface that:

1. edits `scheiber-config.yaml`, starting with Bloc9 devices,
2. provides live Bloc9 discovery from known CAN arbitration ID patterns,
3. is structured to support more Scheiber device types later.

## Task order

1. `bloc9-segment-routing.md`

Completed web UI planning tasks have been moved to `plan/tasks/done/`.

## Current direction

- Keep the existing `scheiber` and `can_mqtt_bridge` packages as the core runtime.
- Extend Bloc9 decoding and control paths to account for remote bus segments.
- Surface segment-aware discovery and control experiments in the setup web UI.
- Treat `/config/scheiber-config.yaml` as the single source of truth.
- Keep local-bus behavior unchanged while making cross-segment behavior explicit.
