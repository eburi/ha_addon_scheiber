# Phantom ON/OFF flapping on Bloc9 4_3 S1/S3 (Buttercup)

Investigation date: 2026-08-07
Installation: `buttercup.local`, add-on `0289ae68_scheiber` v7.0.0, CAN `can1`, MQTT prefix `homeassistant`.
Native `custom_components/scheiber` is **not** installed there; the MQTT add-on bridge is the active path.

## Symptom

`light.scheiber_bathroom` and `light.scheiber_bathroom_spot_lights` alternate ON/OFF in the
Home Assistant UI roughly every 8.5 s. The physical lights never change; they are off the
whole time.

Affected entities:

| HA entity | unique_id | Device | Output | MQTT state topic |
| --- | --- | --- | --- | --- |
| `light.scheiber_bathroom` | `scheiber_bloc9_4_3_s1` | bloc9 bus 4 / segment 3 | S1 | `homeassistant/scheiber/bloc9/4_3/s1/state` |
| `light.scheiber_bathroom_spot_lights` | `scheiber_bloc9_4_3_s3` | bloc9 bus 4 / segment 3 | S3 | `homeassistant/scheiber/bloc9/4_3/s3/state` |

Address byte for bus 4 / segment 3 is `0x80 | (4 << 3) | 3 = 0xA3`.

## Root cause

The Bloc9 is behaving correctly. The add-on decoder is wrong.

`Output.get_state_from_can_message` in `scheiber/src/scheiber/output.py:127` computes:

```python
state = state_bit or brightness > dimming_threshold
```

It reads only the brightness byte and the state byte, and **ignores the mode byte**. When the
Bloc9 reports a stale non-zero brightness setpoint with the ON bits clear, the
`brightness > dimming_threshold` fallback fabricates an ON state.

### Per-output 4-byte layout (observed)

Bytes 0-3 are the lower output (S1/S3/S5), bytes 4-7 the higher output (S2/S4/S6):

| Offset | Meaning |
| --- | --- |
| +0 | brightness |
| +1 | unused / reserved (always `0x00` observed) |
| +2 | mode byte, bit0 = output energised |
| +3 | state byte, bit0 = output energised |

Mode byte values match the documented command mode bytes: `0x00` off, `0x01` full on,
`0x11` PWM on. The observed `0x10` is "PWM configured, not energised".

## Captured evidence

### Faulty output, device 4_3 (`candump -t a -L can1`)

The cycle repeats with a period of ~8.55 s. `000006A3` at ~1 Hz is the normal heartbeat.

```
(1786065777.115174) can1 021606A3#0000000000000101
(1786065778.036734) can1 021806A3#0000000000000000
(1786065778.178551) can1 021606A3#F200100000000101
(1786065779.097286) can1 021806A3#F200100000000000
(1786065785.665164) can1 021606A3#0000000000000101
(1786065786.585994) can1 021806A3#0000000000000000
(1786065786.728644) can1 021606A3#F200100000000101
(1786065787.646855) can1 021806A3#F200100000000000
```

Decoding `021606A3#F200100000000101` (S1/S2 group):

- S1 = bytes 0-3 = `F2 00 10 00` -> brightness `242`, mode `0x10` (bit0 clear), state `0x00` (bit0 clear).
  Both authoritative bits say **OFF**. Decoder returns ON because `242 > 2`.
- S2 = bytes 4-7 = `00 00 01 01` -> brightness `0`, mode `0x01`, state `0x01`.
  Genuinely ON at full brightness. This is the documented "full-on reports brightness 0" quirk.

Decoding `021806A3#F200100000000000` (S3/S4 group):

- S3 = bytes 0-3 = `F2 00 10 00` -> same phantom-ON pattern as S1.

The alternate frame in each cycle is all zeros (`0000000000000000` for the S3/S4 group),
which decodes to OFF. Hence the flapping.

Critically: **the S1/S3 state bit and mode bit are `0` in every frame of the cycle.**
The output is genuinely off at all times, which matches the physical observation.

### Healthy comparison, device `06AA` (bus 5 / segment 2)

```
(1786065781.505479) can1 021606AA#0000000055001101
(1786065781.606762) can1 021606AA#0000000055001109
```

S2 = bytes 4-7 = `55 00 11 01` -> brightness `0x55`, mode `0x11` (PWM on), state `0x01`.
A genuinely dimmed-on light always sets mode bit0 and the state bit.

### No commands from the bridge

No `023606A3` command frames were seen during any capture window. The add-on is not
driving this; the traffic is device-originated.

### Resulting MQTT publications

```
homeassistant/scheiber/bloc9/4_3/s1/state {"state": "OFF", "brightness": 0}
homeassistant/scheiber/bloc9/4_3/s3/state {"state": "OFF", "brightness": 0}
homeassistant/scheiber/bloc9/4_3/s1/state {"state": "ON", "brightness": 242}
homeassistant/scheiber/bloc9/4_3/s3/state {"state": "ON", "brightness": 242}
```

Matching add-on log lines confirm the bridge is faithfully republishing its own bad decode:

```
can_mqtt_bridge.light.master_cabin_light_bathroom - INFO - Published state to homeassistant/scheiber/bloc9/4_3/s1/state: {"state": "ON", "brightness": 242}
```

## Bloc9 firmware version discovery

The Bloc9 heartbeat frame (`0x00000600 | address_byte`, ~1 Hz) carries the firmware
version in bytes 0-2, as hex bytes read as decimal digits:

```
000006A3#0810052CCA
          ^^ ^^ ^^
          08 16 05     0x08 -> 8, 0x10 -> 16, 0x05 -> 5
```

Buttercup inventory (2026-08-07):

| Firmware | Devices |
| --- | --- |
| `08.16.05` | 1, 1_1, 1_2, 1_3, 2, 2_1, 2_2, 2_3, 3, 3_2, 3_3, 4, 4_2, 4_3, 5, 5_3, 6_2, 6_3, 7, 7_2, 8_2, 8_3, 9_3, 10_2 |
| `08.22.01` | 5_2 |

`08.16.05` is the firmware the owner identified as having the turn-on flash defect.
`5_2` is the single outlier, presumably a replaced module.

## Secondary issue: turn-on flash breaks ease-in effects

On firmware `08.16.05` an output that is OFF flashes to full brightness before applying
the requested PWM level, regardless of the previous dim level. This defeats ease-in
transitions.

The bridge is not the cause. `Bloc9Device.send_switch_command`
(`scheiber/src/scheiber/bloc9.py:372`) only emits the full-on mode byte `0x01` when
brightness >= 253; a fade from OFF emits `0x00` then `0x11` PWM steps. The flash is
generated inside the Bloc9.

It is visible on the bus as a full-on report preceding the PWM ramp:

```
10_2 S2  brightness=0    mode=0x01  state=0x01   <- full ON (brightness 0 == full)
10_2 S2  brightness=5    mode=0x11  state=0x01   <- PWM ramp begins
10_2 S2  brightness=10   mode=0x11  state=0x01
10_2 S2  brightness=15   mode=0x11  state=0x01
```

The same leading `mode=0x01` frame was observed on `5_2`, `6_3` and `8_2` during a
group ramp, including on firmware `08.22.01`.

### Not fixable from the bus (confirmed)

The same flash occurs when the light is switched using the boat's physical air switches,
which do not go through this bridge. The defect is therefore in the Bloc9 output energise
path, not in how the command is framed.

The observed sequence is: energise at full brightness, *then* restore the previous PWM
level. Because the firmware demonstrably already knows the target level and flashes
anyway, any scheme that preloads the level before energising cannot help. An earlier
hypothesis that mode `0x10` might act as a "load level without energising" command is
therefore rejected; `0x10` is a status encoding only ("PWM selected, not energised").

Conclusion: **there is no bus-level workaround.** Ease-in effects cannot be made smooth
on firmware `08.16.05` from an OFF start. The only lever that avoids the energise path
entirely is never de-energising the output (holding it at minimum PWM instead of off),
which trades the flash for a permanent faint glow and standby load. Not recommended as a
default; possibly acceptable for a specific scripted scenario.

This does not affect the decoder fix above, which does not rely on the rejected
hypothesis.

## Regression fixtures


Frames to assert against, all `is_extended_id=True`:

| Arbitration ID | Data | Output | Expected state | Expected brightness | Currently returns |
| --- | --- | --- | --- | --- | --- |
| `0x021606A3` | `F2 00 10 00 00 00 01 01` | S1 | `OFF` | `0` | `ON` / `242` (bug) |
| `0x021606A3` | `F2 00 10 00 00 00 01 01` | S2 | `ON` | `255` | `ON` / `255` (ok) |
| `0x021606A3` | `00 00 00 00 00 00 01 01` | S1 | `OFF` | `0` | `OFF` / `0` (ok) |
| `0x021806A3` | `F2 00 10 00 00 00 00 00` | S3 | `OFF` | `0` | `ON` / `242` (bug) |
| `0x021806A3` | `00 00 00 00 00 00 00 00` | S3 | `OFF` | `0` | `OFF` / `0` (ok) |
| `0x021606AA` | `00 00 00 00 55 00 11 01` | S2 | `ON` | `85` | `ON` / `85` (ok) |

## Fix applied

`Output.get_state_from_can_message` now treats the mode byte as authoritative and stops
inferring ON from brightness:

```python
offset = 0 if switch_nr % 2 == 0 else 4
brightness = msg.data[offset]
mode_bit  = (msg.data[offset + 2] & 0x01) == 0x01
state_bit = (msg.data[offset + 3] & 0x01) == 0x01

state = mode_bit or state_bit
if not state:
    brightness = 0
```

Both bits are OR-ed because a 90 s hardware capture across nine devices showed the state
bit lags during dim ramps while the mode bit is already set (16 such frames on 10_2, 3,
3_2, 4_3, 5_2, 6_3, 8_2). Relying on the state byte alone would have broken dimming.
No genuinely-on output was ever observed with mode bit 0 clear, and the only outputs
relying on the old brightness fallback were the two faulty ones:

```
4_3 S1  brightness=3,4,14,16,242  mode=0x10  state=0x00   PHANTOM-ON
4_3 S3  brightness=242            mode=0x10  state=0x00   PHANTOM-ON
```

Applied in both layers:

- `scheiber/src/scheiber/output.py`
- `custom_components/scheiber/core/output.py`

`dimming_threshold` is now unused for state determination. It is retained in the
signature for compatibility and should be removed in a follow-up.

### Test changes

- Replaced `test_dimming_threshold_below` / `test_dimming_threshold_above`, which asserted
  the old brightness fallback using unrealistic mode byte `0x00`.
- Added `test_stale_brightness_with_pwm_mode_off_is_off` reproducing the 4_3 frame.
- Added `test_pwm_mode_bit_set_without_state_bit_is_on` covering the dim-ramp lag.
- Corrected `test_s5_s6_message_format_brightness_and_state`, whose S6 "off" fixture set
  mode byte `0x01` (full on). Real off frames always carry mode `0x00`.

Suite: 187 passed.

## Remaining hardware fault

Decoding is now correct, but 4_3 S1 and S3 are still genuinely de-energised while a stale
PWM setpoint is broadcast at them every 8.55 s. After this fix both entities report a
stable OFF, which matches physical reality, but the lights still cannot be turned on.
That is a separate hardware/configuration fault to chase on the Scheiber side.

## Bloc9 firmware version discovery

The Bloc9 heartbeat frame (`0x00000600 | address_byte`, ~1 Hz) carries the firmware
version in bytes 0-2, as hex bytes read as decimal digits:

```
000006A3#0810052CCA
          ^^ ^^ ^^
          08 16 05     0x08 -> 8, 0x10 -> 16, 0x05 -> 5
```

Buttercup inventory (2026-08-07):

| Firmware | Devices |
| --- | --- |
| `08.16.05` | 1, 1_1, 1_2, 1_3, 2, 2_1, 2_2, 2_3, 3, 3_2, 3_3, 4, 4_2, 4_3, 5, 5_3, 6_2, 6_3, 7, 7_2, 8_2, 8_3, 9_3, 10_2 |
| `08.22.01` | 5_2 |

`08.16.05` is the firmware the owner identified as having the turn-on flash defect.
`5_2` is the single outlier, presumably a replaced module.

## Secondary issue: turn-on flash breaks ease-in effects

On firmware `08.16.05` an output that is OFF flashes to full brightness before applying
the requested PWM level, regardless of the previous dim level. This defeats ease-in
transitions.

The bridge is not the cause. `Bloc9Device.send_switch_command`
(`scheiber/src/scheiber/bloc9.py:372`) only emits the full-on mode byte `0x01` when
brightness >= 253; a fade from OFF emits `0x00` then `0x11` PWM steps. The flash is
generated inside the Bloc9.

It is visible on the bus as a full-on report preceding the PWM ramp:

```
10_2 S2  brightness=0    mode=0x01  state=0x01   <- full ON (brightness 0 == full)
10_2 S2  brightness=5    mode=0x11  state=0x01   <- PWM ramp begins
10_2 S2  brightness=10   mode=0x11  state=0x01
10_2 S2  brightness=15   mode=0x11  state=0x01
```

The same leading `mode=0x01` frame was observed on `5_2`, `6_3` and `8_2` during a
group ramp, including on firmware `08.22.01`.

### Hypothesis: mode `0x10` sets the PWM level without energising

The phantom frames on 4_3 S1/S3 show `mode=0x10` with a non-zero brightness and the
output demonstrably de-energised. That suggests the mode byte decomposes as:

- bit 4 (`0x10`): PWM mode selected
- bit 0 (`0x01`): output energised

so `0x10` means "load the PWM level, stay off" and `0x11` means "PWM at loaded level, on".

If correct, a turn-on from OFF can avoid the flash by sending two commands:

1. `[switch_nr, 0x10, 0x00, target_level]` - preload the level while still off
2. `[switch_nr, 0x11, 0x00, target_level]` - energise at the already-correct level

This is **unverified** and needs a controlled hardware experiment before implementation.
It would also explain 4_3 S1/S3: some panel or scene is repeatedly sending step 1 and
never step 2.

### Open questions

- Does mode `0x10` actually preload the level, or is it merely a status encoding the
  device emits and ignores on receive?
- Does the flash occur on the OFF -> PWM transition only, or on any energise?
- Is the stored level the last PWM level or always full brightness?

## Regression fixtures


Frames to assert against, all `is_extended_id=True`:

| Arbitration ID | Data | Output | Expected state | Expected brightness | Currently returns |
| --- | --- | --- | --- | --- | --- |
| `0x021606A3` | `F2 00 10 00 00 00 01 01` | S1 | `OFF` | `0` | `ON` / `242` (bug) |
| `0x021606A3` | `F2 00 10 00 00 00 01 01` | S2 | `ON` | `255` | `ON` / `255` (ok) |
| `0x021606A3` | `00 00 00 00 00 00 01 01` | S1 | `OFF` | `0` | `OFF` / `0` (ok) |
| `0x021806A3` | `F2 00 10 00 00 00 00 00` | S3 | `OFF` | `0` | `ON` / `242` (bug) |
| `0x021806A3` | `00 00 00 00 00 00 00 00` | S3 | `OFF` | `0` | `OFF` / `0` (ok) |
| `0x021606AA` | `00 00 00 00 55 00 11 01` | S2 | `ON` | `85` | `ON` / `85` (ok) |

## Proposed fix

Treat the mode byte as authoritative alongside the state byte, and stop inferring ON from
brightness alone:

```python
if switch_nr % 2 == 0:
    brightness, mode_byte, state_byte = msg.data[0], msg.data[2], msg.data[3]
else:
    brightness, mode_byte, state_byte = msg.data[4], msg.data[6], msg.data[7]

state = bool(state_byte & 0x01) or bool(mode_byte & 0x01)
if not state:
    brightness = 0
```

Notes and follow-ups:

- Existing tests `test_dimming_threshold_below` and `test_dimming_threshold_above` in
  `scheiber/src/scheiber/tests/test_bloc9_switch_change.py` encode the current fallback with
  mode byte `0x00`. They assert synthetic behaviour that real hardware does not produce and
  must be updated as part of the fix.
- `dimming_threshold` becomes unused for state determination. Decide whether to keep it as a
  brightness floor or remove it from `Output`, `DimmableLight`, `Switch`, and `Pulse`.
- `discovery.py:99` also calls `get_state_from_can_message`, so discovery output benefits too.
- The same fallback exists in the native integration under `custom_components/scheiber/core/`;
  apply the fix in both layers.
- Separately worth understanding why device 4_3 broadcasts a stale `242` setpoint every
  8.55 s. It is harmless once decoding is correct, but it may indicate a Scheiber panel
  holding a stale scene value for these two outputs.
