# Version 4.0.0 - Testing Summary

## Tests Fixed ✅

All existing tests continue to pass with the v4.0.0 changes:
- **54 tests passing** (1 skipped manual hardware test)
- 0 failures
- No changes needed to test files - they test the core logic which remains unchanged

## check_mqtt.py Updated for v4.0.0 ✅

Updated `check_mqtt.py` to validate the new unified device structure:

### Key Changes:

1. **Removed Bloc9 sensor device validation**
   - v3.x had separate Bloc9 sensor devices per bus_id
   - v4.0.0 removes these in favor of unified structure

2. **Updated entity validation** to check for:
   - Device identifiers: `["scheiber_system"]` (unified)
   - Device name: `"Scheiber"`
   - Device model: `"Marine Lighting Control System"`
   - Device manufacturer: `"Scheiber"`
   - **No `via_device` field** (removed in v4.0.0)

3. **Updated output messages** to clearly indicate v4.0.0 structure

### Validation Logic Test

Created `test_check_mqtt_logic.py` to verify the validation works:
```
✅ v4.0.0 config validation: PASS
❌ v3.x config validation: FAIL (correctly rejected)
```

## How to Use check_mqtt.py After Deployment

Once you deploy v4.0.0 to your boat:

```bash
# 1. Update MQTT_HOST in check_mqtt.py if needed (currently: 192.168.55.222)
# 2. Run the validation script
python check_mqtt.py
```

### Expected Output:

```
================================================================================
MQTT DISCOVERY CONFIG VERIFICATION
================================================================================

Loading configuration from ./scheiber.yaml...
✅ Configuration loaded: X bloc9 devices, Y total entities

Listening for messages (3 seconds)...
Found N discovery config topics

================================================================================
DEVICE STRUCTURE: v4.0.0 (Unified Scheiber Device)
================================================================================

All entities belong to a single 'Scheiber' device
Device identifier: scheiber_system

================================================================================
Bloc9 10 - Main Scheiber
================================================================================

  💡 light.scheiber_main_light_saloon_aft (S1):
     Expected topic: homeassistant/light/scheiber_main_light_saloon_aft/config
     ✅ OK

  💡 switch.scheiber_underwater_light (S2):
     Expected topic: homeassistant/switch/scheiber_underwater_light/config
     ✅ OK

  ... (more entities)

================================================================================
SUMMARY
================================================================================

Total checks: N
Passed: N ✅
Failed: 0 ❌

🎉 All discovery configs match scheiber.yaml!
```

## What Gets Validated

For each entity (light/switch), check_mqtt.py verifies:

1. **Discovery topic format**: `homeassistant/{component}/{entity_id}/config`
2. **Entity properties**:
   - Name matches scheiber.yaml
   - Unique ID format: `scheiber_bloc9_{bus_id}_{output}`
3. **MQTT topics**:
   - State: `homeassistant/scheiber/bloc9/{bus_id}/{output}/state`
   - Command: `homeassistant/scheiber/bloc9/{bus_id}/{output}/set`
   - Availability: `homeassistant/scheiber/bloc9/{bus_id}/{output}/availability`
4. **Brightness topics** (for lights only):
   - State: `homeassistant/scheiber/bloc9/{bus_id}/{output}/brightness`
   - Command: `homeassistant/scheiber/bloc9/{bus_id}/{output}/set_brightness`
   - Command type: `brightness`
5. **Device structure** (v4.0.0):
   - Unified device identifier: `scheiber_system`
   - Device name: `Scheiber`
   - Device model: `Marine Lighting Control System`
   - No via_device references

## Breaking Changes in v4.0.0

Users upgrading from v3.x will need to:

1. **Remove old devices** from Home Assistant:
   - Go to Settings → Devices & Services → MQTT
   - Delete all old Scheiber device entries
   - Delete all individual light/switch device entries

2. **Restart the addon** after upgrade

3. **Verify new device appears**:
   - Single "Scheiber - Marine Lighting Control System" device
   - All entities nested under it
   - Clean entity names: `light.scheiber_<name>` instead of `light.<name>_<name>`

4. **Update automations/scripts**:
   - Entity IDs will change due to cleaner naming
   - Example: `light.main_light_saloon_aft_main_light_saloon_aft` → `light.scheiber_main_light_saloon_aft`

## Files Modified

1. `scheiber/config.yaml` - Version bumped to 4.0.0
2. `scheiber/src/devices.py` - Unified device structure implementation
3. `.github/copilot-instructions.md` - Updated documentation
4. `check_mqtt.py` - Updated validation logic for v4.0.0
5. `test_check_mqtt_logic.py` - New test for validation logic

## Testing Checklist

- [x] All unit tests pass (54/54)
- [x] check_mqtt.py logic validated
- [x] Documentation updated
- [ ] Deploy to boat and verify with check_mqtt.py
- [ ] Verify entity naming in Home Assistant
- [ ] Test light controls work
- [ ] Test switch controls work
- [ ] Verify availability tracking works
