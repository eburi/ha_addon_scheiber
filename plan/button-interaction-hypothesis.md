# Scheiber Button Interaction Hypothesis

## Known Context

Scheiber sells Light Air Switch hardware as a very-low-voltage lighting system with wireless and battery-free switches. The public product page describes an included 2.4 GHz interface, one-button and two-button wireless switches, dimming by holding a button, and pairing of switches. Public pages and the local repository do not contain a formal CAN payload specification.

## Confirmed: Wireless Light Air Switch Protocol

Live-captured, controlled evidence (2026-07-05, `buttercup.local`, four-button Air Switch mounted at the bow salon door) confirms the wireless payload schema with high confidence. See `candump_data` captures referenced in the implementation PR for the raw frames.

**Arbitration IDs**: `0x04001A80`, `0x04001A82`, `0x04001A83` (prefix `0x04001A00`, mask `0xFFFFFF00`). Every logical press or release is broadcast redundantly on all three IDs within a few milliseconds, always carrying byte-for-byte identical data. The low byte does not encode a Bloc9 bus/segment target (no evidence ties it to which Bloc9 reacts); it is treated as a fixed redundancy/retransmission scheme of the wireless-to-CAN interface itself. `0x04001A81` has never been observed.

**Payload** (5 bytes): `01 <3-byte identity> <status>`

- Byte 0 is a constant leader byte (`0x01`) marking "wireless button status."
- Bytes 1-3 are a stable per-transmitter-unit identity (e.g. `52 AB 81` for the bow salon 4-button unit, `52 A8 DC` for a distinct single/multi-button unit near the crew cabin). The identity is shared by every button on the same physical Air Switch plate; it does not change across repeated presses or between different buttons on the same unit.
- Byte 4 is the status byte:
  - Bit 7: `1` = pressed, `0` = released.
  - Bits 0-6: a 1-based button index within that physical unit (not a bitmask of simultaneously-active buttons). Confirmed values 1-4 on a 4-button unit map to bottom-left=1, top-left=2, bottom-right=3, top-right=4 (an installer-facing config step is required to learn which physical key is which index; the numbering is not deducible from position alone).

Example (bow salon unit, identity `52AB81`, top-left button, one press+release cycle):

```
04001A82  01 52 AB 81 82   (press: bit7=1, index=2)
04001A80  01 52 AB 81 82
04001A83  01 52 AB 81 82
04001A80  01 52 AB 81 02   (release: bit7=0, index=2)
04001A82  01 52 AB 81 02
04001A83  01 52 AB 81 02
```

Pressing the same physical button repeatedly reproduces the exact same identity+index bytes every time; the toggled on/off outcome is entirely decided by the reacting Bloc9's own programming (confirmed: the bow salon unit's 4 buttons independently toggled Bloc9 outputs on bus 1 (X32 Salon), bus 3 (X226 exterior), and bus 10 segment 2 (X224 bow courtesy light) — a single wireless button can fan out to multiple Bloc9 outputs as a "scene").

This is now implemented: `scheiber/src/scheiber/button_discovery.py:classify_air_switch_message()` decodes it, and `scheiber/src/scheiber/air_switch.py` exposes configured buttons to the MQTT bridge as Home Assistant `event` entities (see `plan/tasks/` for the implementation notes).

## Deferred: Wired Panel/Key Interface

A second, distinguishable family remains observed but intentionally out of scope for now:

- Arbitration IDs vary widely in their own middle+low bytes (e.g. `0x04001808`, `0x04001809`, `0x04001FBA`, `0x04001FB0`, `0x040014B3`, `0x04001F98`, `0x04001F90`, `0x0400149A`, `0x040014BB`).
- Payload is always `00 00 00 01 <status>` — i.e. the identity bytes are constant zero rather than a per-transmitter value. If this family carries an identity at all, it is presumably encoded in the arbitration ID's own middle 16 bits rather than in the payload.
- This shape is easy to distinguish from the wireless family (payload byte 0 is `0x00`, not `0x01`), so the wireless classifier cannot misfire on wired traffic and vice versa.
- Per project direction, this family (believed to be a wired panel/key interface at the electric console) will be addressed later.

## Unconfirmed Companion Messages

Two other message families reliably accompany both wireless and wired button events but their exact semantics remain undetermined and are not required to implement the wireless button feature:

- `0x0402xxxx` (8-byte payload, e.g. `00 FF 00 20 00 00 00 00`): fires multiple times per button event, sometimes repeating ~30ms apart. Not needed for wireless button detection.
- `0x0408xxxx` (6-byte payload): sometimes echoes the *wired* event's own arbitration ID as its first 4 bytes plus the status byte and a trailing constant; this echo has not been reliably observed for wireless (`0x04001A8x`) events in captures so far.

These are left for future investigation and are intentionally not decoded by the current button feature.

## Remaining Unknowns

- Whether every Light Air Switch installation uses the same fixed `0x04001A00` prefix, or whether boats with multiple 2.4 GHz interfaces could see a different prefix per interface.
- Whether button index values can exceed 4 (products with more buttons), or whether index `0` is ever used (e.g. for a single-button switch).
- Long-press/hold semantics for dimming: only quick press/release cycles have been captured so far; whether a held button repeats the pressed frame at some rate, and how that should surface as a Home Assistant event type, is unconfirmed.
- Whether wired key interfaces and wireless Light Air Switch frames could ever share the exact same payload shape on some other installation.
- **Multiple wireless receivers and duplicate reports**: the boat has several Air Switch (SFSP, "Sans Fil Sans Pile") receivers installed. It is not yet understood how the system avoids each receiver independently reporting the same physical press, or whether it does at all (e.g. downstream de-duplication by identity+button_index, physical RF range limiting which receiver hears a given transmitter, or something else). This is a direct target for the guided-capture tooling below: capturing the same physical unit's presses while noting which receivers are nearby should help reveal whether companion frames or accompanying arbitration IDs differ per receiver.

## Tooling Direction

The setup UI's Interactions tab guides an operator through a structured capture of one physical Vimar-framed Air Switch (SFSP) unit at a time:

1. Enter the physical location and the unit's function count: **2** (a single rocker, divided horizontally into top/bottom) or **4** (two rockers side by side, each also divided horizontally, giving top-left/bottom-left/top-right/bottom-right).
2. The tool walks through each function in turn (2-function: top, then bottom; 4-function: top-left, bottom-left, top-right, bottom-right) with an explicit instruction to press and release that function several times before moving on. Repetition matters in practice: presses are sometimes missed entirely (weak piezo kinetic energy, or an obstructed radio path to the receiver), and releases are occasionally dropped, which can leave a light stuck mid-dim.
3. For every function, the tool records every button-source CAN frame (matched broadly, not just the confirmed wireless shape, so any unexpected wired-panel activity during the session is still visible for context), every resulting Bloc9/panel reaction, and any unconfirmed companion frames from the same `0x04xxxxxx` family (e.g. `0x0402xxxx`/`0x0408xxxx`) that reliably accompany button events but whose meaning is not decoded yet.
4. When a function's captured frames match the confirmed wireless schema, the tool shows the decoded identity and button index live, flags if more than one distinct identity/button-index pair was seen for a single function (a sign of a misfire, a stray second unit, or more than one receiver reporting independently), and offers a ready-to-copy `air_switch` configuration snippet.
5. Finishing a session appends the complete capture (every step, every frame, every reaction) as one JSON line to an `interactions_log.jsonl` file in the add-on's data directory, so data collected across many physical units and multiple visits can be analyzed offline later, rather than only inspected live in the browser.

`scheiber/src/tools/analyze_air_switch_log.py` reads that log file and prints, per session, the confirmed identity/button-index pairs and reactions seen for each function, plus a cross-session summary grouping every observed identity across all saved captures - a starting point for confirming whether the bit layout is consistent across different physical units, and for investigating the multiple-receiver duplicate-report question above.
