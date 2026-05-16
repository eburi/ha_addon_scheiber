# Task: setup-editor-unassigned-output-workflow

## Title

Support preconfigured outputs in the setup editor

## Depends on

- `bloc9-output-metadata-model`

## Objective

Update the setup editor workflow so an operator can add a Bloc9, enter device name and description, give names to outputs that are not yet in use, save that work, and later come back to assign light or switch roles without losing the saved labels.

## Needed changes

- update the config API contract so `/api/config` and `/api/config/apply` expose preserved metadata for disabled outputs,
- adjust frontend form state and save logic so output names survive when role is set to disabled,
- make validation and inline messaging explain which fields are optional before role assignment and which fields become required once a role is chosen,
- review the device list and editor summary so partially configured Bloc9 devices are represented clearly instead of looking empty or discarded,
- add focused web-app tests for load/edit/save flows that keep disabled-output metadata intact.

## Constraints

- Do not create Home Assistant entities for outputs that still have no role.
- Keep the current add/edit Bloc9 workflow recognizable for already configured devices.
- Avoid implying that an output is active on the CAN runtime when only its metadata has been saved.

## Deliverables

- updated editor behavior for partially configured Bloc9 devices,
- API and UI validation rules for role-less outputs,
- tests proving disabled-output labels survive round trips through the editor.
