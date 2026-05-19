# Task: sourceselector-ac-monitoring

## Title

Add read-only SourceSelector AC monitoring

## Depends on

- `scheiber-address-family-model`

## Objective

Treat the observed AC voltage/frequency frames as SourceSelector measurements instead of Bloc7 levels, and expose them as read-only configurable sensors with clear safety boundaries.

## Discovery basis

- The selector troubleshooting document identifies the Source Selector as the AC actuator used to switch between shore and generator sources.
- The selector hardware includes shore input, generator input, AC output, voltage measurement, AC current measurement, CAN bus, and 110-230 V AC 50-60 Hz power supply.
- The Lagoon guide describes multiple power source selectors, including standard shore/generator/inverter selection and optional 125A shore/HVAC contexts.
- Live frames `0x02040B9A` and `0x02040BA9` show paired AC-looking values:
  - voltage bytes around `235` or `240`,
  - frequency bytes around `50`,
  - inactive slots as `0V/0Hz`.

## Needed changes

- add a `source_selector` device family/type for read-only AC measurements,
- keep all SourceSelector control/relay behavior out of scope,
- classify `0x02040Bxx` candidates as SourceSelector AC measurement frames rather than Bloc7 raw/level frames,
- support paired voltage/frequency channel definitions in configuration,
- include optional labels such as converter, generator, shore-power, and unknown source without hardcoding assignments,
- add safety wording in the setup UI that high-power AC switching must not be controlled or tested from this bridge.

## Constraints

- No CAN command-sending APIs for SourceSelector in this task.
- Do not change relay or source selection state.
- Keep measurements configurable because Ship Control assignments may be wrong after boat configuration changes.
- Preserve existing unknown-frame inspection for unrecognized SourceSelector routes.

## Deliverables

- read-only SourceSelector runtime/config model,
- Home Assistant sensor publication for AC voltage and frequency,
- setup UI candidate cards for SourceSelector measurements,
- tests proving SourceSelector candidates are not presented as Bloc7 level sensors.
