# Task: frontend-browser-heartbeat

## Title

Add browser heartbeat cleanup for frontend-only runtime activity

## Depends on

- `frontend-workflow`
- `runtime-integration`

## Objective

Track active setup web UI browsers and automatically stop frontend-only services such as Bloc9 discovery and CAN inspector capture when the last browser stops heartbeating.

## Needed changes

- add a server-side browser session monitor with heartbeat expiry and cleanup callbacks,
- expose setup web API endpoints for browser heartbeat refresh and disconnect,
- send regular heartbeats from the setup UI and standalone inspector page,
- stop discovery and inspector capture when all browser sessions have expired,
- cover multi-browser and timeout behavior with focused tests.

## Constraints

- Keep the shared bridge runtime running even when no browser is connected.
- Do not let one expired browser session stop frontend activity while another browser is still active.
- Keep embedded inspector usage tied to the main setup page heartbeat instead of creating conflicting duplicate sessions.

## Deliverables

- backend browser heartbeat monitor and API routes,
- web UI heartbeat wiring for setup and standalone inspector flows,
- automatic cleanup for frontend-only discovery and inspection services,
- regression tests for heartbeat expiry and cleanup behavior.
