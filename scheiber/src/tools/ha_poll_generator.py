#!/usr/bin/env python3
"""Poll HA entities every second via supervisor API; log changes + periodic heartbeat."""

import json
import os
import sys
import time
import urllib.request

out = sys.argv[1]
ENTITIES = [
    "binary_sensor.generator_running",
    "sensor.victron_mqtt_system_0_system_ac_active_input_source",
    "sensor.victron_mqtt_vebus_276_vebus_inverter_active_input",
    "sensor.victron_mqtt_vebus_276_vebus_inverter_state",
    "sensor.victron_mqtt_vebus_276_vebus_inverter_input_voltage_l1_2",
    "sensor.victron_mqtt_vebus_276_vebus_inverter_input_frequency_l1_2",
    "sensor.victron_mqtt_vebus_276_vebus_inverter_input_power_l1_2",
    "sensor.victron_mqtt_vebus_276_vebus_inverter_input_current_l1_2",
    "sensor.victron_mqtt_system_0_system_generator_load_l1_2",
    "sensor.victron_mqtt_vebus_276_vebus_inverter_dc_power",
    "sensor.victron_mqtt_system_0_system_dc_battery_power",
    "sensor.snowdrop_generator_battery_voltage",
    "switch.scheiber_bloc9_x28_s1",
    "switch.scheiber_bloc9_x28_s2",
    "binary_sensor.scheiber_stale_outputs",
]
tok = os.environ["SUPERVISOR_TOKEN"]
f = open(out, "a", buffering=1)
last = {}
hb = 0
while True:
    ts = time.time()
    try:
        req = urllib.request.Request(
            "http://supervisor/core/api/states",
            headers={"Authorization": f"Bearer {tok}"},
        )
        states = json.load(urllib.request.urlopen(req, timeout=5))
        cur = {s["entity_id"]: s["state"] for s in states if s["entity_id"] in ENTITIES}
    except Exception as e:
        f.write(f"({ts:.3f}) ERROR {e}\n")
        time.sleep(2)
        continue
    for k in ENTITIES:
        v = cur.get(k)
        if last.get(k) != v:
            f.write(f"({ts:.3f}) CHANGE {k} {last.get(k)} -> {v}\n")
            last[k] = v
    if ts - hb > 30:
        hb = ts
        f.write(
            f"({ts:.3f}) HB "
            + " ".join(f"{k.split('.')[-1]}={cur.get(k)}" for k in ENTITIES)
            + "\n"
        )
    time.sleep(1)
