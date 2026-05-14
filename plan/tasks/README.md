# Scheiber web interface tasks

These task files turn the web interface plan into reviewable, commit-friendly work items.

## Goal

Add a Home Assistant add-on web interface that:

1. edits `scheiber-config.yaml`, starting with Bloc9 devices,
2. provides live Bloc9 discovery from known CAN arbitration ID patterns,
3. is structured to support more Scheiber device types later.

## Task order

1. `web-ui-architecture.md`
2. `config-editor-api.md`
3. `discovery-pipeline.md`
4. `frontend-workflow.md`
5. `runtime-integration.md`
6. `test-strategy.md`

## Current direction

- Keep the existing `scheiber` and `can_mqtt_bridge` packages as the core runtime.
- Add a Python web app layer inside the add-on for API and UI delivery.
- Expose the UI through Home Assistant ingress.
- Treat `/config/scheiber-config.yaml` as the single source of truth.
- Keep discovery read-only and driven by live CAN observation.
