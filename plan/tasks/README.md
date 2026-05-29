# Scheiber web interface tasks

These task files track follow-up work for the delivered web interface and related setup tooling.

## Goal

Keep the setup workflow moving toward a Home Assistant add-on web interface that:

1. edits `scheiber-config.yaml`, starting with Bloc9 devices,
2. provides live Bloc9 discovery from known CAN arbitration ID patterns,
3. preserves pre-configuration metadata for devices and outputs before roles are assigned,
4. is structured to support more Scheiber device types later,
5. can onboard Bloc7 analog sensors using decoded route grouping while preserving manual matcher confirmation,
6. can surface read-only SourceSelector AC measurements and battery/IBS candidates without adding unsafe control paths.

## Task order

No active implementation tasks are pending.

Completed planning tasks have been moved to `plan/tasks/done/`.

## Current direction

- Keep the existing `scheiber` and `can_mqtt_bridge` packages as the core runtime.
- Treat `/config/scheiber-config.yaml` as the single source of truth for both active entities and setup-time metadata.
- The setup editor now preserves operator-entered output names even when an output is still disabled or not yet assigned as a light or switch.
- Bloc9 decoding and control paths account for remote bus segments.
- The setup web UI surfaces segment-aware discovery and control experiments.
- Add an opt-in MCP surface on the management runtime so AI tools can inspect live CAN traffic and edit validated configuration during setup and reverse engineering.
- Keep local-bus behavior unchanged while making cross-segment behavior explicit.
- The shared low-byte route model `0x80 | (bus_id << 3) | segment_id` is used across known Scheiber families, with message-family classification kept separate from route decoding.
- Bloc7 manual matcher workflows remain backward compatible while supporting route-aware grouping for documented Lagoon Bloc7 devices.
- SourceSelector AC observations are treated as read-only measurements; relay/source switching control is intentionally out of scope.
- Version 6.2.0-compatible Bloc9 behavior is preserved because only Bloc9 was used in field deployments before these newer setup workflows.
- MQTT discovery names should follow the configured entity/topic slug so Home Assistant generates specific entity ids on first discovery.
