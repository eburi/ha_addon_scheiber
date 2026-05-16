# Task: bloc9-output-metadata-model

## Title

Persist Bloc9 output metadata before role assignment

## Objective

Define and implement the configuration shape needed to save a Bloc9 device, its device-level description, and per-output labels even when some outputs are still disabled and have not yet been assigned a runtime role.

## Needed changes

- decide the canonical YAML shape for pre-configured Bloc9 outputs so `scheiber-config.yaml` can store setup-time output metadata without forcing every saved output into `lights` or `switches`,
- update `scheiber.config` load, validation, normalization, and serialization logic so disabled outputs keep user-entered metadata instead of being reset to blank values,
- keep runtime-facing device creation compatible with the existing light/switch model so unassigned outputs do not create MQTT entities or CAN control surfaces,
- define backward-compatible handling for existing v6 configs that only use `lights` and `switches`,
- add or update tests that cover round-tripping disabled outputs with names, mixed configured and unconfigured outputs, and save/load compatibility.

## Constraints

- Preserve existing active light and switch behavior.
- Do not require an `entity_id` until an output has a concrete role.
- Keep `/config/scheiber-config.yaml` as the only persisted source of truth.
- Avoid introducing a config shape that forces the runtime layer to care about editor-only UI state.

## Deliverables

- documented Bloc9 config shape for unassigned outputs,
- config validation and serialization rules for preserved disabled-output metadata,
- compatibility plan for legacy configs,
- test coverage for the new persistence behavior.
