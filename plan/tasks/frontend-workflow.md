# Task: frontend-workflow

## Title

Design web interface workflow

## Depends on

- `config-editor-api`
- `discovery-pipeline`

## Objective

Plan the frontend screens and state flow for device list, Bloc9 editor forms, validation feedback, save/apply actions, and discovery mode results so the UI is usable on a new boat during setup.

## Primary screens

1. configuration overview
2. Bloc9 device list
3. add/edit Bloc9 device form
4. discovery mode
5. save/apply status view

## Required flows

- open and inspect current config,
- create or edit a Bloc9 device,
- add lights and switches to `s1`-`s6`,
- validate before save,
- promote a discovered bus ID into a prefilled Bloc9 form,
- apply changes and see bridge restart/reload outcome.

## UX principles

- optimize for setup and mapping, not day-to-day control,
- keep discovery separate from destructive actions,
- surface validation inline and clearly,
- avoid hiding YAML/model constraints from the operator.

## Deliverables

- page/component map,
- frontend state model,
- interaction flow for discovery-to-config promotion,
- save/apply feedback states.
