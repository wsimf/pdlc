Spike the delivery tasks below against current source and return an implementation-ready plan for each task that needs one.

{{INCLUDE:shared/execution-boundary.md}}
Bounded, read-only codebase exploration is the only delegation allowed.
Work from this brief. Author the plans and return the plan files and manifest to the calling agent.

## Work item `{{PARENT_WORK_ITEM}}`

--- BEGIN WORK ITEM ---

{{PARENT_BODY}}

--- END WORK ITEM ---

## Tasks

The open, unimplemented tasks for this work item, lowest in the stack first.

{{#IF UNPLANNED_TASKS}}
- No plan yet ({{UNPLANNED_TASKS}}): plan these from scratch.
{{/IF}}
{{#IF PLANNED_TO_CHECK}}
- Already planned ({{PLANNED_TASKS}}): check each against the {{CHANGE_SOURCES}} below. Re-plan only the ones that are out of date, starting from the existing plan.
{{/IF}}
{{#IF PLANNED_SETTLED}}
- Already planned ({{PLANNED_TASKS}}): leave these alone. They are here as context for the tasks you plan.
{{/IF}}
{{#EACH TASKS}}

### `{{TASK_TAG}}` {{TASK_TITLE}} (#{{TASK_NUMBER}})

--- BEGIN TASK ---

{{TASK_BODY}}

--- END TASK ---
{{#IF EXISTING_PLAN}}

This task already has a plan:

--- BEGIN EXISTING PLAN ---

{{EXISTING_PLAN}}

--- END EXISTING PLAN ---
{{/IF}}
{{/EACH}}
{{#IF CHANGE_SOURCES}}

## Changes needed

The {{CHANGE_SOURCES}} below apply to this pass. They take precedence over everything above except the task bodies.

- Re-plan each task they affect. Start from its current plan and change only what they ask for.
- Leave tasks they don't affect alone, and don't return them.
- If they ask for something the task body doesn't allow, say so in the plan. Don't plan outside the task's scope.
- If you can't tell which task they mean, stop and report it.
{{#IF CHANGE_REQUESTS}}

### Change requests

Findings recorded against this stage since it last published.

--- BEGIN CHANGE REQUESTS ---

{{CHANGE_REQUESTS}}

--- END CHANGE REQUESTS ---
{{/IF}}
{{#IF DRIVER_FOLLOWUP}}

### Driver follow-up

A change the driver asked for, or findings from a review of your plans, verbatim.

{{DRIVER_FOLLOWUP}}
{{/IF}}
{{/IF}}

{{INCLUDE:shared/plan-design.md}}

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
