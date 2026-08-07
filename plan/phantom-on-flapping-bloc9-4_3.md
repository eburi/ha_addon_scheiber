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

## Live command test (2026-08-07): Bloc9 4_3 stuck in hold-to-dim cycle

Owner insight: Scheiber air switches implement brightness adjustment as *press and hold* ->
the Bloc9 runs a continuous dimming cycle until the button is released. Bloc9 4_3 appears
stuck in that mode.

A controlled test via MQTT confirms this.

### ON command

Published `{"state":"ON","brightness":128}` to `homeassistant/scheiber/bloc9/4_3/s1/set`.

```
023606A3#00110080              <- bridge command: S1, PWM mode, level 0x80
021606A3#8000110000000000      <- device accepts, level 0x80, mode 0x11
021606A3#9400110100000000      <- then ramps up autonomously
021606A3#A900110100000000
021606A3#C200110100000000
021606A3#DF00110100000000
021606A3#0000010900000000      <- full on (brightness 0 == full, mode 0x01)
021606A3#F200110900000000      <- then ramps down
021606A3#D300110900000000
  ... continuous triangle wave, ~142 ms per step ...
021606A3#0200110100000000      <- minimum
021606A3#0300110100000000      <- and back up again, indefinitely
```

Key points:

- The command **is** received and applied correctly. The device is not deaf.
- Immediately afterwards the Bloc9 resumes an autonomous triangle-wave dim cycle.
- Cycle period ~11.3 s (full-on peaks at t+386.05, t+397.32, t+408.59).
- During the cycle mode is `0x11` and state is `0x01`/`0x09`, i.e. genuinely energised.
  The lamp physically ramps up and down; the owner confirmed this visually.

### OFF command

```
023606A3#00000000              <- bridge command: S1 off
021606A3#0000000000000000      <- device turns off, cycle stops
021606A3#0F00100000000000
021606A3#0000000000000000      <- returns to idle phantom pattern
021606A3#F200100000000000
```

OFF reliably stops the cycle and returns the output to the idle pattern
(`mode=0x10`, brightness alternating 0/242 every 8.55 s, de-energised).

### Revised understanding

The idle `mode=0x10` pattern is the stuck dim cycle running while the output is *not*
energised. Energising the output makes the same cycle visible on the lamp.

This also revises the earlier note that the outputs "cannot be turned on": they can, they
simply refuse to hold a level. The channel hardware is fine.

The decoder fix behaves correctly in both phases: stable OFF while idle
(`mode=0x10`), and ON with a ramping brightness while cycling (`mode=0x11`).

### Firmware update not available

Per a Scheiber technician, updating Bloc9 firmware requires special hardware. Debug or
programming pins have not been identified on a physically damaged spare unit. So a
firmware fix is not currently an option.

### Proposed remedy procedure (untested)

If the Bloc9 is stuck waiting for an air-switch *release* event, delivering one may end the
cycle. Two variants, in order of preference:

1. **Physical**: locate the air switch bound to this output, press and release it, and
   capture the bus. If the cycle stops, record the exact frames as a remedy.
2. **Synthetic**: once the identity and button index of that air switch are known from
   step 1, replay the release frame
   (`0x04001A80/82/83`, 5 bytes, `01 <identity[3]> <index>` with bit 7 clear) to clear the
   state without physical access. This would make the remedy scriptable.

Note the air switch receivers are alive and healthy on Buttercup
(`0x00001A80/82/83`, ~1 Hz heartbeat, payload `08 01 00 63 15`, firmware `08.01.00`),
but no air switches are configured in `scheiber-config.yaml`, and no press frames were
seen in a 45 s idle capture. A historical press is recorded in `/data/button_capture.log`
with identity `52AB81`, button index 2.

## RESOLVED: air switch press clears the stuck dim cycle

Date: 2026-08-07. A capture session with the owner pressing the physical air switch
**cleared the stuck state**. Verified afterwards: a 40 s capture produced **zero**
`0x021606A3` / `0x021806A3` frames, where previously the phantom cycle emitted four
frames every 8.55 s. All six outputs of 4_3 now report a stable OFF.

### Remedy procedure

When a Bloc9 output pair is caught in a stuck dim cycle (idle signature:
`mode=0x10`, brightness alternating between `0` and a stale value on a fixed period,
output de-energised):

1. Identify the air switch button bound to the affected output (see mapping method below).
2. Press and release it once. A normal short press is enough.
3. Confirm the fix by capturing the affected device's status IDs for ~40 s. Silence means
   the cycle has stopped; the device only emits status frames on change.

A command sent over MQTT/CAN does **not** clear the state, and in fact re-triggers the
runaway ramp. Only the air switch path cleared it.

### Air switch mapping for transmitter 52B75B (Bloc9 4_3)

| Button index | Bloc9 output | Entity |
| --- | --- | --- |
| 1 | S4 | Cabin Entrance Ambient Light |
| 2 | S5 | Cabin Entrance Light |
| 3 | S2 | Shower |
| 4 | **S1 + S3** | Bathroom **and** Bathroom Spot Lights (the stuck pair) |
| 6 | none observed | unexplained, see below |

Button 4 drives S1 and S3 **together**, which is why exactly those two outputs were stuck
as a pair. During a press-and-hold both ramp continuously but in **anti-phase**: S1 falls
while S3 rises, then they reverse. The idle phantom showed the same anti-phase relationship
(S1 at 242 while S3 at 0), confirming the phantom was this same dim cycle running while
de-energised.

Release stops the ramp and both outputs hold their current level, so the hold-to-dim
feature itself works correctly.

### Protocol discovery: receiver relays presses to a targeted Bloc9

Alongside the broadcast press frames on `0x04001A80/82/83`, the receiver emits a
**device-targeted** relay frame:

```
0x040806A3#0152B75B8403
     ^^        ^^^^^^ ^^
     |         identity  status (0x84 = press, button 4)
     low byte 0xA3 = bus 4 / segment 3
```

So the family is `0x04080600 | address_byte`, payload `01 <identity[3]> <status> 03`.
Other observed targets: `0x04020F81`, `0x040214BB` with a different `00FF..` payload shape.

Only presses are relayed; the relay repeats while the button is held and stops on release.
This is how hold-to-dim is communicated to the Bloc9.

**This suggests a scriptable remedy**: replaying a single `0x040806A3#0152B75B8403` frame
may clear a stuck cycle without physical access. Untested, and it would send a real press
to real hardware, so it needs a deliberate test before being relied upon.

### Air switch reliability

Of the press frames that reached the CAN bus, the Bloc9 reacted almost every time:

| Button | Press frames on bus | Bloc9 reacted | Rate |
| --- | --- | --- | --- |
| 1 | 6 | 5 | 83% |
| 2 | 11 | 10 | 91% |
| 3 | 7 | 7 | 100% |
| 4 | 13 | 12 | 92% |
| 6 | 1 | 0 | 0% |

Important caveat: this only measures presses whose frames **arrived on the bus**. A press
lost over the radio produces no frame at all and is invisible here. The owner reports the
two left-hand buttons failing often; assuming a clockwise press order starting top-left,
those are buttons 2 and 1, which are also the two lowest rates above. The conclusion is
that the perceived failures are **radio reception**, not a CAN or Bloc9 fault.

Button index 6 appeared four times with no Bloc9 reaction and no relay frame. Note
`6 == 2 | 4`, so this may be a simultaneous two-button press rather than a distinct
function. Unresolved.

## CONFIRMED: air switch presses can be simulated on the bus

Date: 2026-08-07. Synthetic frames were injected with `cansend` and verified against the
physical outputs. **A press is simulated by the broadcast press/release pair only.**

### Working method

```sh
# button status byte: 0x80 | button_index   (0x81=btn1 ... 0x84=btn4)
# release status byte: the same with bit 7 cleared
cansend can1 04001A80#0152B75B84     # press,   transmitter 52B75B, button 4
cansend can1 04001A83#0152B75B84
sleep 0.34
cansend can1 04001A80#0152B75B04     # release
cansend can1 04001A83#0152B75B04
```

Both the press **and** the release must be sent. The gap of ~340 ms matches a real short
press. Only low bytes `0x80` and `0x83` are needed; the physical receivers were observed
using `0x80`/`0x82`/`0x83` inconsistently and the Bloc9 acts on the first it sees.

### Verification results

Every button toggled its mapped outputs correctly, on and off:

| Simulated | Expected | Observed | Result |
| --- | --- | --- | --- |
| btn4 press 1 | S1+S3 ON | `021606A3#FF001100`, `021806A3#FF001100` -> both 255 | pass |
| btn4 press 2 | S1+S3 OFF | both `mode=0x00` | pass |
| btn3 press | S2 toggle | `S2 = FF 00 11 01` -> ON 255 | pass |
| btn2 press 1 | S5 ON | `021A06A3#FF001100` -> ON 255 | pass |
| btn2 press 2 | S5 OFF | `021A06A3#00000001` -> OFF | pass |
| btn1 press 1 | S4 ON | `021806A3#...FF001100` -> ON 255 | pass |
| btn1 press 2 | S4 OFF | `021806A3#...00000001` -> OFF | pass |

This confirms the button-to-output mapping and makes the remedy scriptable.

### Correction: `0x040806A3` is emitted BY the system, not sent to it

An earlier note suggested replaying `0x040806A3#0152B75B8403` as the remedy. That was
wrong and is retracted:

- When only the broadcast pair is injected, `0x040806A3` **appears on the bus by itself**,
  emitted in response. It is a reaction, not a stimulus.
- A real toggle-off was captured with **no** `0x040806A3` frame at all
  (t=121.219 in the session log), proving it is not required to drive the output.
- Injecting `0x040806A3` alone did trigger the outputs once, but every repeat was ignored,
  and a full sequence including it produced no reaction at all. It is not a reliable path.

Use the broadcast pair.

### Caution

These frames are indistinguishable from a real button press, so anything else bound to the
same transmitter and button will also react. Verify the binding before injecting, and
remember that a press is a **toggle**: the resulting state depends on the current state.

### Air switch button 6 explained

Button index 6 is very likely a simultaneous press of two stacked buttons: `6 == 2 | 4`,
and the owner notes the press was made low on the rocker, catching the button below.
The status byte therefore appears to be a **bitmask of active buttons**, not an ordinal
index. This also explains why index 6 produced no Bloc9 reaction and no relay frame.

