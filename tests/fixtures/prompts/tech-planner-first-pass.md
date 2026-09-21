Spike the delivery tasks below against current source and return an implementation-ready plan for each task that needs one.

## Execution boundary

You are being invoked as a leaf worker for this one planning pass.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Bounded, read-only codebase exploration is the only delegation allowed.
Work from this brief. Author the plans and return the plan files and manifest to the calling agent.

## Work item `60`

--- BEGIN WORK ITEM ---

## Product

### 4. Functional requirements
- FR-1: The record lands.
- FR-2: The record publishes.

### 5. Constraints
- C-1: Commands own every mutation.

## UI

UJ-1 covers the first run.

## Decisions
- none

## Open Questions
- none

--- END WORK ITEM ---

## Tasks

The open, unimplemented tasks for this work item, lowest in the stack first.

- No plan yet (TASK-002): plan these from scratch.
- Already planned (TASK-001): leave these alone. They are here as context for the tasks you plan.

### `WORK-60-TASK-001` [CORE] Core work (#601)

--- BEGIN TASK ---

## Scope
Build the seam.

Covers FR-1.

## Acceptance criteria
- it works

--- END TASK ---

This task already has a plan:

--- BEGIN EXISTING PLAN ---

Touch one module.

--- END EXISTING PLAN ---

### `WORK-60-TASK-002` [UI] Second (#602)

--- BEGIN TASK ---

## Scope
Show it.

Covers FR-2, UJ-1.

## Acceptance criteria
- it shows

--- END TASK ---

## Designing the plan

Plan the approach, not the code: name where the change goes and what it affects, and leave types, signatures, and line-level edits to the implementer.

- Plan the change as if the task's requirement had been in the design from the start. Don't bolt it onto the current shape when the current shape is what makes it awkward.
- Name the module that owns the new behaviour. Put a decision behind one source of truth rather than repeating it across several places.
- Subtract before you add. When the task replaces existing behaviour, plan the removal first when it simplifies what follows, or alongside its replacement.
- When the task replaces an internal API, plan to migrate its callers and delete the old one in the same task. Don't plan a compatibility shim kept only for internal callers.
- Prefer the smallest change that satisfies the task. Don't plan a wrapper, layer, or abstraction with one caller, or thread a new signal through types, schemas, or pipelines when a direct path exists.
- Where the codebase has no precedent for a decision, name the alternative you rejected and why.
- Look for what the change can break beyond its call sites: persisted data, wire formats, config, flags, and code that reads the same data. Name the one fact the change's safety depends on and the check that proves it.
- When the task touches a command, lifecycle step, or anything that can be retried or run concurrently, state what happens if it runs twice or stops halfway.

Where one of these and a task conflict, say so in the plan rather than planning around it.

## Return

Return a plan only for each task you plan or re-plan. Each plan is heading-free and covers:

- files and modules that will change
- interfaces and call sites
- sequencing and inter-task dependencies
- migration and rollback risk
- test / validation strategy mapped to the task's acceptance criteria
- unresolved decisions, called out explicitly

Don't restate scope, non-goals, dependencies, coverage, or acceptance criteria. The task body already carries them.

Return one plan file per task, plus a manifest:

```json
[{ "id": "TASK-003", "plan": "/tmp/plan-003.md" }]
```

A missing prerequisite, or a decision only the driver can make, stops the pass: report it exactly and don't guess.
