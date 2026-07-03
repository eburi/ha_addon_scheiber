# Scheiber Button Interaction Hypothesis

## Known Context

Scheiber sells Light Air Switch hardware as a very-low-voltage lighting system with wireless and battery-free switches. The public product page describes an included 2.4 GHz interface, one-button and two-button wireless switches, dimming by holding a button, and pairing of switches. Public pages and the local repository do not contain a formal CAN payload specification.

## Local Evidence

Observed local captures include two probable button-source families:

- `0x04001A80`: labelled in old notes as wireless buttons / Light Air Switch interface.
- `0x04001808`: labelled in old notes as a button panel at the electric console or key interface.

Examples:

- `0x04001A80 01 54 45 1F 82` followed by `0x04001A80 01 54 45 1F 02` during a wireless button press/release.
- `0x04001A80 01 53 E8 86 83` followed by `0x04001A80 01 53 E8 86 03` during another wireless button press/release.
- `0x04001808 00 00 00 01 85` followed by `0x04001808 00 00 00 01 05` during a panel/key interaction.

These examples suggest compact five-byte status payloads where the final byte carries button state bits and the preceding bytes carry some observed switch/interface identity. In the wireless examples, bit 7 in the final byte appears to distinguish pressed from released while lower bits remain associated with the active button or button group.

## Working Hypothesis

The physical button does not command Bloc9 directly on the CAN bus. Instead:

- A radio/key interface receives the physical interaction.
- The interface emits a CAN status frame containing a payload identity plus bitwise button state.
- A pressed button changes one or more status bits from `0` to `1`; release returns those bits to `0`.
- Bloc9 devices listen for these status frames according to their own programming.
- Bloc9 outputs then emit normal state-update frames (`0x021606xx`, `0x021806xx`, `0x021A06xx`) when their outputs change.
- Holding a button keeps the pressed state active long enough for Bloc9 programming to run dimming cycles until the key-up status arrives.

## Unknowns

- Whether the first four bytes are a globally unique switch transmitter ID, a learned radio code, an interface-local mapped ID, or a mixed identity/status field.
- Whether Scheiber can produce indefinitely many unique button identities, or whether the 2.4 GHz interface maps physical transmitters into a bounded local ID table during pairing.
- Whether wired key interfaces and wireless Light Air Switch frames share exactly the same payload schema.
- Which lower status bits encode button number for two-button and four-button switches, and how simultaneous presses are represented.
- Whether the high bit always means pressed, or only in the observed families.

## Tooling Direction

The setup UI now has an Interactions tab that records evidence without assuming the unknown schema is solved. It captures:

- the operator-entered physical location,
- probable button-source frames and payload identities,
- status-byte rising/falling bits for key-down/key-up inference,
- five seconds of pre-trigger raw CAN context,
- up to ten seconds of Bloc9 reaction output changes and dimming cycles.

This should let future captures compare many installed buttons and decide whether the identity bytes are stable transmitter IDs, learned pairing slots, or another addressing scheme.
