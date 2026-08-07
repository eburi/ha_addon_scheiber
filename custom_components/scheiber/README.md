# Scheiber CAN Home Assistant Integration

This custom integration connects Home Assistant directly to a SocketCAN interface using `python-can` and bundles the existing client-agnostic Scheiber CAN core from this repository.

Discovery-only and read-only modes are enabled by default. In that mode the integration observes CAN traffic, creates network diagnostic entities, records arbitration IDs, discovers Bloc9/Bloc7/AirSwitch candidates, and exposes observed Bloc9 outputs as safe read-only switch entities.

To send commands or expose full dimming/effects, disable discovery-only mode and point the integration at a Scheiber YAML config that marks outputs as lights or switches. Read-only mode still blocks CAN writes.

Home Assistant does not allow custom integrations to add arbitrary Settings sidebars without a custom frontend panel. The integration instead uses device registry entries, diagnostics, and sensors with message/device tables in attributes.
