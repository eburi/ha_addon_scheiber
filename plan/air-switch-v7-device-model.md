# AirSwitch v7 Device Model

## Goals

- Treat wireless Scheiber AirSwitch/SFSP units as first-class devices, not as anonymous buttons under one global Scheiber device.
- Keep discovery running until the user explicitly stops it. Browser session cleanup must not stop AirSwitch discovery.
- Persist discovered AirSwitch identities, indexes, press/release observations, CAN-ID variants, and rough reaction evidence while discovery is running.
- Let users progressively complete configuration from observed data: name a discovered index, choose whether it is published, and safely apply those changes to `scheiber-config.yaml` with runtime reload.
- Use stable topology-derived IDs:
  - AirSwitch device unique id: `scheiber_air_switch_<identity>`.
  - AirSwitch button entity unique id: `scheiber_air_switch_<identity>_button_<index>`.
- Use this as a model for a later Bloc9 refactor where Bloc9 devices become Home Assistant devices and outputs become topology-derived entities.

## Home Assistant Entity Type

For incoming physical wireless button presses, MQTT `event` is the best ordinary entity type:

- MQTT `button` is for commands sent from Home Assistant to a device, so it is the wrong direction.
- MQTT `device_automation` is useful for automation triggers and explicitly intended for remotes/buttons, but it does not create normal entities the same way and is discovery-only.
- MQTT `event` creates stateless entities for physical events and supports `device_class: button`; it fits battery-less AirSwitch presses and can be attached to per-AirSwitch HA devices.

The v7 bridge should publish MQTT `event` entities for published AirSwitch indexes. A future enhancement may additionally publish MQTT `device_automation` triggers for users who prefer HA device-trigger automations.

## Runtime Config Shape

New v7 shape:

```yaml
devices:
  - type: air_switch
    identity: "52AB81"
    name: "Bow Salon AirSwitch"
    buttons:
      1:
        name: "Bottom Left"
        published: true
      2:
        name: "Top Left"
        published: true
      3:
        name: "Bottom Right"
        published: true
      4:
        name: "Top Right"
        published: true
      5:
        name: "Both Bottom?"
        published: false
```

Compatibility:

- The v6.14 list shape with `buttons: [{identity, button_index, name, entity_id}]` should be accepted and normalized into v7 grouped-by-identity devices during load/editor conversion.
- `entity_id` is no longer required for AirSwitch. HA entity identity is guaranteed by stable `unique_id`; entity IDs can be customized by HA users.

## Discovery State Shape

Persisted in the add-on data directory as `air_switch_discovery.json`:

```json
{
  "running": true,
  "updated_at": 1783875871.0,
  "air_switches": {
    "52AB81": {
      "identity": "52AB81",
      "first_seen_at": 1783325579.9,
      "last_seen_at": 1783875871.0,
      "can_ids": {"0x04001A80": 120, "0x04001A82": 122, "0x04001A83": 64},
      "indexes": {
        "1": {"press_count": 10, "release_count": 10, "last_seen_at": 1783875868.8},
        "2": {"press_count": 10, "release_count": 10, "last_seen_at": 1783875855.4}
      }
    }
  }
}
```

Discovery records confirmed wireless AirSwitch frames only for the device/index model. Companion frames and guided-session logs remain useful protocol evidence, but the configuration model should be driven by confirmed `(identity, index)` observations.

## Default Labels

For discovered indexes, default labels should remain editable and conservative:

- If indexes `{1, 2}` are seen: `1=Bottom`, `2=Top`.
- If indexes `{1, 2, 3, 4}` are seen: `1=Bottom Left`, `2=Top Left`, `3=Bottom Right`, `4=Top Right`.
- Indexes outside that pattern use `Index <n>` until the user renames them.

The observed `5` for bow-salon bottom-right is deliberately not auto-labelled as a chord yet. It can be configured as `published: false` while evidence is collected.

## Safe Config Apply

The web UI should send the current config revision with AirSwitch updates. The server should:

1. Load current editor config and revision.
2. Verify the caller's base revision matches.
3. Upsert only AirSwitch devices/indexes requested by the UI.
4. Save atomically using existing config helpers.
5. Reload runtime through `BridgeRuntimeController.reload()`.
6. Roll back on reload failure using existing `config_ops.apply_editor_config()` behavior.

This preserves the existing safe config workflow while allowing discovery state to progressively complete the model.
