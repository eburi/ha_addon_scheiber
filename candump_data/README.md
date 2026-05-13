# Generator Start/Stop/Status CAN Capture Method

This document describes a reliable method to capture CAN traffic and correlate it with Home Assistant signals so you can identify which CAN messages correspond to generator start, stop, and running state.

## Goal

Create synchronized logs for:

1. Raw CAN frames
2. Home Assistant charger input power (or another generator proxy signal)
3. Manual action markers (start command sent, stop command sent, etc.)

With these three timelines, you can correlate events and isolate candidate CAN IDs and byte patterns.

## Why This Works

- `candump` gives frame-level data with timestamps.
- Home Assistant gives behavior-level state (for example when power appears/disappears).
- Manual markers tie your intentional actions to exact times.

Repeated start/stop cycles let you filter out noise and keep only patterns that appear consistently.

## Prerequisites

- `can-utils` installed (provides `candump`)
- `jq` installed (for parsing Home Assistant API JSON)
- Home Assistant long-lived access token
- System clock synced (NTP)
- A writable capture directory

## 1. Create a Session Folder

```bash
mkdir -p ./candump_data/sessions
SESSION="$(date -u +%Y%m%dT%H%M%SZ)"
BASE="./candump_data/sessions/$SESSION"
mkdir -p "$BASE"
echo "Session: $SESSION"
```

## 2. Start CAN Capture

Use absolute timestamps with date so correlation is straightforward.

```bash
candump -D -d -t A -L any | stdbuf -oL tee "$BASE/can.log"
```

Notes:

- `-t A`: absolute timestamp with date
- `-L`: stable log format on stdout
- `-D`: do not exit when a CAN device goes down
- `-d`: monitor dropped frames
- `any`: capture from all CAN interfaces

If you only want one interface, replace `any` with `can0` or `can1`.

## 3. Start Home Assistant Power Capture (Parallel Terminal)

Capture the signal that indicates generator behavior, for example charger input power.

```bash
HA_URL="http://127.0.0.1:8123"
TOKEN="YOUR_LONG_LIVED_TOKEN"
ENTITY="sensor.charger_input_power"

while true; do
	TS="$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
	VAL="$(curl -s \
		-H "Authorization: Bearer $TOKEN" \
		-H "Content-Type: application/json" \
		"$HA_URL/api/states/$ENTITY" | jq -r '.state')"
	echo "$TS power=$VAL"
	sleep 1
done | stdbuf -oL tee "$BASE/ha_power.log"
```

## 4. Write Manual Markers (Third Terminal)

Write markers exactly when you trigger generator actions.

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ) MARK TEST_START" >> "$BASE/markers.log"
echo "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ) MARK GEN_START_CMD_SENT" >> "$BASE/markers.log"
echo "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ) MARK GEN_STOP_CMD_SENT" >> "$BASE/markers.log"
echo "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ) MARK TEST_END" >> "$BASE/markers.log"
```

Recommended marker names:

- `TEST_START`
- `GEN_START_CMD_SENT`
- `GEN_STOP_CMD_SENT`
- `TEST_END`

## 5. Perform Controlled Test Cycles

Run multiple repeatable cycles, for example:

1. Idle for 2 minutes
2. Send generator start command
3. Run for 5 minutes
4. Send generator stop command
5. Idle for 2 minutes

Repeat at least 5 to 10 cycles.

## 6. Correlate Data

Use Home Assistant power changes and marker timestamps as anchors.

For each start/stop event:

1. Find transition time in `ha_power.log`
2. Inspect CAN frames in a time window around it (for example +/- 15 seconds)
3. Collect CAN IDs that always change near start events
4. Collect CAN IDs that always change near stop events
5. Compare across all cycles and remove one-off IDs

Candidate generator status messages usually show one or more of these traits:

- Same CAN ID appears around every start and every stop
- Specific bytes/bitfields flip predictably
- Messages repeat periodically while generator is running

## 7. Data Quality Checklist

- Use UTC everywhere (`date -u`)
- Keep captures on the same machine when possible
- Check `candump -d` output for dropped frames
- Record one session per file set
- Include notes on anomalies in a session note file

## 8. Optional: Focused Second Pass

After discovery run(s), capture a focused set with candidate ID filters to reduce noise.

Example filter usage (replace IDs/masks with real candidates):

```bash
candump -D -d -t A -L can0,123:7FF,456:7FF | stdbuf -oL tee "$BASE/can_filtered.log"
```

## Suggested Session File Layout

```text
candump_data/sessions/<timestamp>/
	can.log
	ha_power.log
	markers.log
	notes.md
```

## Quick Start Summary

1. Start `candump` with `-t A -L`
2. Start Home Assistant signal logging with UTC timestamps
3. Add manual markers for start/stop actions
4. Run multiple controlled cycles
5. Correlate by timestamp and keep repeatable CAN patterns

