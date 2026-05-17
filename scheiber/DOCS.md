# Scheiber

## How it works

This add-on connects a Scheiber SocketCAN bus interface to Home Assistant using
MQTT Discovery.

At runtime it:

1. reads Scheiber CAN traffic from the configured Linux CAN interface,
2. decodes supported devices such as Bloc9 outputs,
3. publishes state and availability to MQTT topics,
4. exposes configured entities to Home Assistant through MQTT Discovery.

When the setup UI is enabled, the add-on also provides an ingress page inside
Home Assistant for:

- discovering likely Bloc9 devices from live traffic,
- editing and validating `scheiber-config.yaml`,
- testing mappings before saving them.

## First start

1. Add the repository URL in **Settings -> Add-ons -> Add-on Store -> Repositories**.
2. Install **Scheiber**.
3. Configure MQTT access and the correct CAN interface.
4. Start the add-on.
5. Open the add-on UI in Home Assistant to discover devices and save your
   `scheiber-config.yaml`.
6. Once configured, Home Assistant will create entities automatically through
   MQTT Discovery.

## Configuration

| Option | Description | Default |
|---|---|---|
| `can_interface` | SocketCAN interface to monitor and control | `can1` |
| `mqtt_host` | MQTT broker hostname | `localhost` |
| `mqtt_port` | MQTT broker port | `1883` |
| `mqtt_user` | MQTT username | `mqtt_user` |
| `mqtt_password` | MQTT password | `mqtt` |
| `mqtt_topic_prefix` | MQTT discovery/state prefix | `homeassistant` |
| `log_level` | Logging verbosity | `info` |
| `data_dir` | Directory for persisted state and runtime data | `/data` |
| `config_file` | Scheiber entity configuration file path | `/config/scheiber-config.yaml` |
| `web_ui_enabled` | Enable the ingress setup UI | `true` |
| `mcp_server_enabled` | Enable MCP access for AI-assisted setup and CAN inspection | `false` |

## Example `scheiber-config.yaml`

```yaml
devices:
  - type: bloc9
    bus_id: 7
    name: Salon Bloc9
    lights:
      s1:
        name: Salon Working Light
      s2:
        name: Salon Reading Light
    switches:
      s3:
        name: Water Pump
```

Only outputs you explicitly configure are exposed to Home Assistant.

## Home Assistant behavior

- Entities are created via MQTT Discovery.
- All configured entities belong to a single Scheiber device in Home Assistant.
- State is retained across restarts from the add-on data directory.
- The setup UI is available through Home Assistant ingress when
  `web_ui_enabled` is turned on.

## Safety notes

- Start by exposing only non-critical outputs.
- Keep emergency, navigation, and safety-critical circuits out of Home Assistant.
- The optional MCP server exposes configuration editing and live CAN inspection;
  enable it only temporarily during setup or reverse engineering.
- If `web_ui_enabled` is off, the management runtime is not started, so MCP
  access is not available.

## Support

- Project repository: <https://github.com/eburi/ha_addon_scheiber>
- Issues: <https://github.com/eburi/ha_addon_scheiber/issues>
