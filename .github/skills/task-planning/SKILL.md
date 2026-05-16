---
name: task-planning
description: Breaks a feature request into planning task files under plan/tasks/. Use this when asked to plan a feature, write implementation tasks, or turn a feature description into a task breakdown. If no feature description is provided, ask for it before creating files.
---

Use this skill when the user wants a feature planned rather than implemented.

## Goal

Turn the requested feature into a small set of concrete task files in `plan/tasks/` that match this repository's existing planning format.

## Process

1. Identify the feature to plan.
   - If the user did not provide a usable feature description, ask for a short description of the feature before making any file changes.
   - Do not guess a feature when the prompt is too vague.
2. Review the current planning context before writing files.
   - Read `plan/tasks/README.md`.
   - Read any existing task files that overlap with the requested feature so you can avoid duplicates and preserve useful dependencies.
3. Create or update planning files in `plan/tasks/`.
   - Prefer one task file per meaningful workstream.
   - Use lowercase kebab-case filenames such as `plan/tasks/<task-name>.md`.
   - Update an existing task file instead of creating a duplicate when the work already has a matching task.
4. Keep the task breakdown implementation-oriented but still planning-level.
   - Focus on deliverable chunks of work, dependencies, constraints, and expected outputs.
   - Do not start implementing the feature unless the user explicitly asks for implementation.
5. Update `plan/tasks/README.md` when you add new active tasks.
   - Add a short goal statement if needed.
   - List the active task files in the intended execution order.
   - Do not move unrelated tasks to `done/` unless the user explicitly asks for task cleanup.

## Task file format

Match the existing style used in this repository. Prefer this structure:

```md
# Task: <task-name>

## Title

<human-readable title>

## Depends on

- `<other-task-name>`

## Objective

<what this task must achieve>

## Needed changes

- <concrete planning item>
- <concrete planning item>

## Constraints

- <important limitation or compatibility requirement>

## Deliverables

- <expected output>
```

Notes:

- Omit the `Depends on` section if there are no dependencies.
- If another section name fits the task better, keep the overall style consistent with existing files in `plan/tasks/`.
- Write for future implementation work: concise, specific, and easy to execute.

## Planning rules for this repository

- Keep plans inside `plan/tasks/`.
- Respect the project architecture in `AGENTS.md` and `.github/copilot-instructions.md`.
- Prefer a few well-scoped tasks over many tiny tasks.
- Call out cross-cutting work explicitly when it spans CAN runtime, MQTT bridge, web UI, config migration, or testing.
- Preserve existing active tasks unless the new plan clearly replaces them.

## Expected result

After using this skill, the repository should contain:

1. new or updated task files in `plan/tasks/` for the requested feature, and
2. an updated `plan/tasks/README.md` that points to those task files in a sensible order.
