# Task: mqtt-discovery-entity-naming

## Title

Align MQTT discovery names with entity topic slugs

## Depends on

- None

## Objective

Make Home Assistant MQTT Discovery publish each entity `name` from the same configured slug that is already used in the discovery topic path, so new Home Assistant entity ids become specific enough for cabin-level naming.

## Scope

- Keep the existing configuration schema unchanged.
- Keep MQTT discovery topic paths, state topics, command topics, and unique IDs unchanged.
- Derive the published discovery `name` from the configured `entity_id` / topic slug instead of the shorter display label.
- Apply the same naming rule to lights, switches, and sensors.

## Implementation direction

- Add one shared helper in `scheiber/src/can_mqtt_bridge/` that converts slugs like `owners_cabin_light_shower` into `Owners Cabin Light Shower`.
- Use that helper from the MQTT discovery publishers in:
  - `scheiber/src/can_mqtt_bridge/light.py`
  - `scheiber/src/can_mqtt_bridge/switch.py`
  - `scheiber/src/can_mqtt_bridge/sensor.py`
- Update discovery tests in `scheiber/src/can_mqtt_bridge/tests/test_bridge.py` to assert the new published names.
- Bump the add-on patch version and add a changelog entry for the user-visible naming change.

## Notes

- Existing Home Assistant entities may keep their old entity ids because Home Assistant uses `unique_id` to track registered entities. This task changes the discovery payload for new discovery and does not attempt an entity-registry migration.

## Expected result

For a discovery topic like `homeassistant/light/owners_cabin_light_shower/config`, the published config should use:

```json
{
  "name": "Owners Cabin Light Shower"
}
```

If the configured slug later becomes `master_cabin_light_shower`, the published config should use:

```json
{
  "name": "Master Cabin Light Shower"
}
```

## Completion notes

- Added a shared MQTT discovery-name formatter that derives discovery `name` from the configured entity slug.
- Updated light, switch, and sensor discovery publishers to use the formatted entity slug while preserving unique IDs and MQTT topic paths.
- Updated bridge tests to cover descriptive discovery names and bumped the add-on patch version to `6.10.4`.
