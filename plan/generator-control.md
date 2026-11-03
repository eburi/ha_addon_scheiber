# Generator control over the Scheiber bus

Investigation date: 2026-10-26, live on `snowdrop.local` (add-on 7.1.1, `can1`), two
controlled start/stop cycles, plus five cycles mined from
`candump_data/24h_of_scheiber/snowdrop_candump_20260308.candump`. Session extract:
`candump_data/generator_sessions/20261026T154102Z/`.

## Result

The Scheiber control panel starts and stops the Onan generator through a Scheiber
node at address byte `0x88` in the `0x0B` message family. That family is already
modelled in the add-on as the read-only `source_selector` device
(`scheiber/src/scheiber/protocol.py`, `SOURCE_SELECTOR_*` prefixes). `0x88` decodes
to `bus_id=1`, `segment_id=0`.

The node drives two relay outputs wired to the Onan remote start and stop lines:

| Action | Panel command frame | Node reaction |
| --- | --- | --- |
| Start | `0x02460B88` data `01` | Output 1 ON for **30.0 s**, then OFF |
| Stop  | `0x02460B88` data `02` | Output 2 ON for **60.0 s**, then OFF |

No RS485 or other serial link is involved on the Scheiber side. All seven observed
cycles are identical to within 0.1 s on the relay timings.

## Frames sent by node `0x0B88`

| CAN ID | Rate | Meaning |
| --- | --- | --- |
| `0x00000B88` | 1 Hz | Heartbeat, payload `08 0F 00 FB 03` (constant) |
| `0x02040B88` | ~2 Hz | AC measurement, 8 bytes: `[genV u16be][genHz u16be][srcV u16be][srcHz u16be]`. Bytes 0-3 are the generator output (0/0 while stopped, ramps to ~240 V / 50 Hz within ~10 s of start). Bytes 4-7 are the second AC source (inverter/AC bus), 220-240 V / 50 Hz continuously. Short transients with nonsense Hz values (e.g. 1050) appear in the second after a stop; clamp or ignore values outside 40-70 Hz. |
| `0x02060B88` | ~2 Hz | Generator starter battery voltage, u16be in 0.1 V (`0x0090` = 14.4 V). Dips to ~10.5 V during cranking. |
| `0x02160B88` | on change | Relay output state, same 8-byte layout as the Bloc9 S1/S2 frame: bytes 0-3 output 1 (start relay), bytes 4-7 output 2 (stop relay); byte +2 mode and +3 state, `01 01` when energised. |
| `0x02440B88` | on change | Control phase byte: `02` start pulse active, `03` start pulse + feedback bit, `01` start pulse done (running), `05` stop pulse active, `04` stop pulse continuing, `00` stop pulse done (stopped). |
| `0x02140B88` | on change | Engine/feedback state byte. Bit 0 = generator running (set 5-9 s after start, cleared ~1.9 s after stop command, just before generator AC collapses). Bit 2 always set. Bit 4 is a transient during start (`0x14` at +0.7 s, `0x15` at +9.5 s); bit 3 a transient during stop (`0x0D`). |
| `0x02400B88`, `0x02420B88` | rare | Seen a handful of times in the March capture, not around start/stop. Unknown, ignore. |

### Observed cycle timeline (all seven cycles)

Start (`t0` = command frame):

| Offset | Event |
| --- | --- |
| +0.00 s | `0216` output 1 ON, `0244` = `02` |
| +0.7 s | `0214` = `14`, `0244` = `03` |
| +2.5 s | `0214` = `04`, `0244` = `02` |
| +5 to +9 s | `0214` = `05` (running bit set) |
| +8 to +11 s | `0204` generator V first non-zero, 50 Hz |
| +9.5 to +12.6 s | `0214` = `15`, `0244` = `03` |
| +10 to +14 s | generator V >= 200 |
| +24 to +28 s | Quattro switches from inverting to bulk (Victron, via HA) |
| +29.93 s | `0216` output 1 OFF, `0244` = `01` |

Stop:

| Offset | Event |
| --- | --- |
| +0.00 s | `0216` output 2 ON, `0244` = `05` |
| +0.2 s | `0214` = `05`, then `0244` = `04` at +0.26 s |
| +1.9 s | `0214` = `04` (running bit cleared) |
| +2.1 to +2.3 s | `0204` generator V = 0 |
| +1 to +3 s | Quattro back to inverting, AC input not connected |
| +59.86 s | `0216` output 2 OFF, `0244` = `00` |

The panel's "stopping" animation ends when output 2 releases at +60 s.

## Victron side (via Home Assistant)

`sensor.victron_mqtt_vebus_276_vebus_inverter_input_frequency_l1_2` and
`..._input_voltage_l1_2` show the generator feed on AC-in 1; `..._inverter_state`
goes `inverting -> sustain/bulk` on start and back on stop;
`sensor.victron_mqtt_system_0_system_ac_active_input_source` goes `generator`.
These are useful as an independent "running" cross-check but lag the bus by 15-25 s
on start. The existing HA template `binary_sensor.generator_running` never changed
during either run and needs fixing separately (not part of the add-on).

## Implementation plan

Status: implemented in add-on 7.2.0 (`scheiber/src/scheiber/generator.py`,
`scheiber/src/can_mqtt_bridge/generator.py`). The steps below are kept as the design record.

Keep the layer boundaries: protocol and command logic in `scheiber/src/scheiber/`,
MQTT entities in `scheiber/src/can_mqtt_bridge/`. Commands must go through
`ScheiberCanBus.send_message`, which already enforces `read_only`.

1. **Protocol constants** (`protocol.py`): add `SOURCE_SELECTOR_COMMAND_PREFIX = 0x02460B00`,
   `SOURCE_SELECTOR_OUTPUT_STATE_PREFIX = 0x02160B00`, `SOURCE_SELECTOR_PHASE_PREFIX = 0x02440B00`,
   `SOURCE_SELECTOR_ENGINE_STATE_PREFIX = 0x02140B00`, `SOURCE_SELECTOR_DC_PREFIX = 0x02060B00`,
   command bytes `GENERATOR_CMD_START = 0x01`, `GENERATOR_CMD_STOP = 0x02`, and extend
   `classify_message_family` with the new families.
2. **Device model** (`source_selector.py`): add an optional `generator` section to
   `SourceSelectorDevice`. When present the device:
   - sends `[cmd]` on `0x02460B00 | address_byte` via `can_bus.send_message`
     (`start()` / `stop()`), logging at INFO;
   - decodes `0x0216` output state with `Output.decode_output_frame` to track
     `start_pulse_active` / `stop_pulse_active`;
   - decodes `0x0214` bit 0 into `running`, `0x0244` into `phase`;
   - refuses `start()` while running or while either pulse is active, and `stop()`
     while stopped or while a pulse is active, with a WARNING (the panel firmware
     presumably has the same interlock; do not rely on the Onan to ignore it);
   - exposes `running`, `phase`, `start_pulse_active`, `stop_pulse_active` through the
     existing observer pattern, and persists nothing for them (always re-derived
     from the bus; `0x0214`/`0x0244` are only sent on change, so after a restart
     treat `running` as unknown until the first frame, or derive it from
     `0x0204` generator frequency > 0, which repeats at 2 Hz).
   - Built-in sensors when `generator:` is configured, without per-sensor matcher
     config: generator voltage, generator frequency (both u16be from `0x0204`,
     sanity-clamped), battery voltage (`0x0206`, scale 0.1). Keep the existing
     free-form `sensors:` list working for other installations.
3. **Config** (`config.py`, `scheiber/src/scheiber/__init__.py` factory): accept
   ```yaml
   - type: source_selector
     bus_id: 1
     name: Generator interface
     generator:
       name: Generator
       entity_id: generator
   ```
   Validate and round-trip it through the editor/runtime converters; the
   `/config/scheiber-config.yaml` on snowdrop has no `source_selector` entry yet, so
   add one there as part of the rollout.
4. **MQTT entities** (`can_mqtt_bridge/`): for a device with a `generator` section,
   publish
   - `switch.scheiber_generator` (state from `running`; ON -> `start()`, OFF -> `stop()`),
     plus `button.scheiber_generator_start` / `..._stop` reusing `MQTTButton`-style
     command handling for people who prefer explicit buttons;
   - `binary_sensor.scheiber_generator_running` (`device_class: running`) and a
     diagnostic `sensor.scheiber_generator_phase` with the decoded phase name;
   - sensors for generator voltage, frequency, and starter battery voltage through
     `MQTTSensor`.
   Honour `read_only` in all command paths and discard retained commands older than
   300 s like `MQTTButton` does, so a broker replay can never start the generator.
5. **Tests** (mock bus): command frame bytes and ID for bus 1 and for a segmented
   address; interlock refusals; decoding of `0x0216`, `0x0214`, `0x0244`, `0x0204`,
   `0x0206` using the frames in this document; `read_only` blocking; MQTT discovery
   payloads and command dispatch.
6. **Docs and release**: README SourceSelector section (it currently states the
   bridge sends no SourceSelector commands), `scheiber/CHANGELOG.md` `[Unreleased]`,
   bump `scheiber/config.yaml` to 7.2.0 (minor, backward-compatible feature).

## Open points

- Meaning of `0x0244`/`0x0214` transient bits is inferred from timing only. Treat
  them as diagnostics, not as control inputs.
- Behaviour of a start command while the stop pulse is still active (or vice versa)
  was not tested on purpose. The interlock above avoids sending it.
- Whether the panel itself also reacts to a start command sent by the add-on (e.g.
  shows the start animation) is untested; expected yes, since it only observes the
  node's `0x0216`/`0x0244` frames.
