# Scheiber web interface tasks

These task files track follow-up work for the delivered web interface and related setup tooling.

## Goal

Keep the setup workflow moving toward a Home Assistant add-on web interface that:

1. edits `scheiber-config.yaml`, starting with Bloc9 devices,
2. provides live Bloc9 discovery from known CAN arbitration ID patterns,
3. preserves pre-configuration metadata for devices and outputs before roles are assigned,
4. is structured to support more Scheiber device types later,
5. can onboard Bloc7 analog sensors even when device identity must start from manually confirmed CAN matchers instead of fully known segment-aware ID rules.

## Task order

1. `bloc9-segment-routing.md`

Completed planning tasks have been moved to `plan/tasks/done/`.

## Current direction

- Keep the existing `scheiber` and `can_mqtt_bridge` packages as the core runtime.
- Treat `/config/scheiber-config.yaml` as the single source of truth for both active entities and setup-time metadata.
- The setup editor now preserves operator-entered output names even when an output is still disabled or not yet assigned as a light or switch.
- Extend Bloc9 decoding and control paths to account for remote bus segments.
- Surface segment-aware discovery and control experiments in the setup web UI.
- Add an opt-in MCP surface on the management runtime so AI tools can inspect live CAN traffic and edit validated configuration during setup and reverse engineering.
- Keep local-bus behavior unchanged while making cross-segment behavior explicit.
- Keep the new Bloc7 manual matcher workflow honest about uncertainty until segment placement and arbitration-ID extraction rules are understood well enough to automate safely.
