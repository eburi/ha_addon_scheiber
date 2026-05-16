# Task: runtime-integration

## Title

Plan runtime and add-on integration

## Depends on

- `web-ui-architecture`
- `config-editor-api`
- `discovery-pipeline`

## Objective

Plan add-on manifest, Docker image, startup script, and process supervision changes required to expose the web UI, keep the bridge running, and support config reload or restart behavior safely.

## Current state

- `scheiber/config.yaml` defines add-on options and startup behavior.
- `scheiber/Dockerfile` builds a Python environment and copies `/src`.
- `scheiber/run.sh` configures CAN interfaces, runs migrations, and then `exec`s the bridge.

## Needed changes

- expose a web UI through Home Assistant add-on features,
- start the web server alongside the bridge,
- coordinate bridge reload or restart after config apply,
- preserve migration behavior and CAN setup,
- keep shutdown clean for both web and bridge runtimes.

## Key decisions

1. single process with embedded web server vs supervised multiple processes,
2. in-process bridge reload vs full process restart,
3. how startup failures are surfaced when one subsystem fails,
4. whether the UI remains available during bridge restart.

## Deliverables

- startup/lifecycle design,
- add-on manifest updates,
- Docker/runtime requirements,
- failure-handling strategy for apply/restart operations.
