---
name: task-implementation
description: Implements a planned task from plan/tasks/, validates it with the repository's existing checks, and when complete moves the task file to plan/tasks/done/ while updating related planning documents. Use this when asked to implement a planned task or complete work described by an existing task file.
---

Use this skill when the work is already planned in `plan/tasks/` and the user wants execution rather than more planning.

## Goal

Implement one planned task end-to-end, validate the result with the repository's existing checks, then mark the planning artifacts as completed.

## Process

1. Identify the task to implement.
   - Accept a task name, task filename, or a clear reference to an existing plan item.
   - If the user did not identify a specific planned task, ask which `plan/tasks/*.md` item should be implemented before changing files.
2. Read the planning context first.
   - Read the target task file in `plan/tasks/`.
   - Read `plan/tasks/README.md`.
   - Read any directly related task files if the target lists dependencies or if adjacent tasks share the same work area.
   - Review `AGENTS.md` and `.github/copilot-instructions.md` guidance relevant to the touched code.
3. Implement the task completely.
   - Make code and configuration changes in the correct layer for this repository.
   - Reuse existing abstractions and preserve current behavior outside the planned change.
   - Update any user-facing documentation or config examples that are directly affected.
4. Run the repository's existing validation commands appropriate to the change.
   - Prefer the existing Poe tasks:
     - `poe lint`
     - `poe test`
     - `poe check`
   - If a narrower existing test command is sufficient for the touched area, use it, but do not skip validation.
   - Do not invent new test frameworks or ad hoc validation steps when repository commands already exist.
5. Only after the implementation is complete and checks pass, update the planning artifacts.
   - Move the completed task file from `plan/tasks/<task-name>.md` to `plan/tasks/done/<task-name>.md`.
   - Update `plan/tasks/README.md` to remove the task from the active order and keep the goal/current direction accurate.
   - Update any remaining active task files that reference the completed task in `Depends on`, assumptions, or sequencing notes.
   - If the completed task changes what future tasks should do, update those task files rather than leaving stale guidance behind.
6. Finish with a clean task state.
   - Keep unrelated active tasks in place.
   - Do not move a task to `done/` if implementation is partial, blocked, or if validation is failing.

## Repository-specific implementation rules

- Respect the repo architecture:
  - CAN and device behavior lives in `scheiber/src/scheiber/`.
  - MQTT and Home Assistant bridge behavior lives in `scheiber/src/can_mqtt_bridge/`.
  - Setup web UI and related flows should stay in their existing web layer.
- For user-facing add-on changes, update both:
  - `scheiber/config.yaml` version following semver, and
  - `scheiber/CHANGELOG.md` in Keep a Changelog format.
- Keep `scheiber-config.yaml` and other example or setup docs aligned when behavior or configuration changes.
- Do not mark the task complete until code, tests, and planning documents all reflect the finished state.

## Expected result

After using this skill, the repository should contain:

1. the implemented code and documentation changes,
2. passing existing validation for the change,
3. the completed task moved to `plan/tasks/done/`, and
4. updated planning documents that no longer present the finished task as active work.
