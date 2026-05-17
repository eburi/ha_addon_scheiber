# Task: bloc7-runtime-config

## Title

Wire Bloc7 devices into the runtime and configuration model

## Objective

Make Bloc7 a first-class configured device type in the runtime so analog sensors can be loaded from `scheiber-config.yaml`, restored from persisted state, and published through the existing MQTT sensor bridge without requiring any guessed segment-aware ID extraction.

## Needed changes

- add Bloc7 to the supported device-type list used by config validation and runtime loading,
- define the canonical Bloc7 YAML shape for configured sensors, including:
  - device identity fields,
  - sensor role/type metadata,
  - explicit matcher input,
  - explicit byte extraction/scaling metadata,
- wire `create_scheiber_system()` and device factory paths so `type: bloc7` creates `Bloc7Device` instances,
- ensure persisted state keys remain stable for Bloc7 devices even when arbitration-ID mapping is still manual,
- confirm the existing MQTT bridge path can create Home Assistant sensor entities from configured Bloc7 sensors without special-case hacks,
- keep the runtime shape compatible with later discovery-assisted setup work instead of baking reverse-engineered assumptions directly into `Bloc7Device`.

## Constraints

- Do not assume a reliable Bloc7 `bus_id` or `segment_id` extraction rule yet.
- Treat explicit configured matchers as the source of truth until live evidence is strong enough to automate more of the identity model.
- Preserve current Bloc9 behavior and current config semantics unchanged.
- Keep CAN protocol decoding in `scheiber/src/scheiber/` and MQTT/Home Assistant concerns in `scheiber/src/can_mqtt_bridge/`.

## Deliverables

- runtime support for `type: bloc7` devices loaded from config,
- a documented Bloc7 config schema centered on explicit sensor definitions,
- stable persistence and bridge wiring for configured Bloc7 sensors.
