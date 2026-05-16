# Task: config-editor-api

## Title

Design configuration editor backend

## Depends on

- `web-ui-architecture`

## Objective

Design backend endpoints and server-side validation for reading, editing, validating, and persisting `scheiber-config.yaml`, starting with Bloc9 devices and leaving room for additional device types.

## Scope

- Read current config from `/config/scheiber-config.yaml`.
- Validate and normalize YAML before saving.
- Write config atomically.
- Return structured validation errors for the UI.

## First device schema

For Bloc9, support:

- `type`
- `bus_id`
- optional `name`
- optional `description`
- `lights`
- `switches`
- per-output `name`
- per-output `entity_id`

## Validation rules

- device type must be supported,
- `bus_id` must be present and unique per device type,
- output names must stay within `s1` through `s6`,
- `entity_id` values must be unique,
- malformed YAML must not be written,
- unsupported keys should be rejected or surfaced clearly.

## Deliverables

- API contract for get/validate/save actions,
- config domain model that can grow with future device types,
- atomic write strategy,
- UI-facing error response format.
