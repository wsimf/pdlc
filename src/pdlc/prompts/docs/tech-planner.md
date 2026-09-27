Spike the delivery tasks below against current source and write an implementation-ready plan for each task that needs one.

{{INCLUDE:shared/execution-boundary.md}}
Bounded, read-only codebase exploration is the only delegation allowed.
Work from this brief. Write the plans into the task files below and report back to the calling agent.

## Work item `{{PARENT_WORK_ITEM}}`

--- BEGIN WORK ITEM ---

{{PARENT_BODY}}

--- END WORK ITEM ---

## Your Task

The manifest at `{{MANIFEST_PATH}}` names one file for each open, unimplemented task of this work item, lowest in the stack first. Each file holds the task body between `--- BEGIN TASK ---` and `--- END TASK ---`, then its plan between `--- BEGIN TECH PLAN ---` and `--- END TECH PLAN ---`.

Write each plan in place, between its tech plan markers, replacing the placeholder comment in a task with no plan yet. Everything else is read-only: don't edit the task body, the markers, or the manifest, and add nothing outside the two blocks. A change the task body needs is a blocker to report, not an edit.

{{#EACH TASKS}}
- `{{TASK_ID}}` — {{TASK_TITLE}} ({{TASK_STATUS}}): `{{TASK_FILE}}`
{{/EACH}}

{{#IF UNPLANNED_TASKS}}
- No plan yet ({{UNPLANNED_TASKS}}): plan these from scratch.
{{/IF}}
{{#IF DRAFTED_TASKS}}
- Drafted, not yet landed ({{DRAFTED_TASKS}}): the plan in each file is an earlier pass's draft. Start from it and revise it in place; don't plan these from scratch.
{{/IF}}
{{#IF PLANNED_TO_CHECK}}
- Already planned ({{PLANNED_TASKS}}): check each against the {{CHANGE_SOURCES}} below. Re-plan only the ones that are out of date, starting from the existing plan.
{{/IF}}
{{#IF PLANNED_SETTLED}}
- Already planned ({{PLANNED_TASKS}}): leave their plans unchanged. They are here as context for the tasks you plan.
{{/IF}}
{{#IF CHANGE_SOURCES}}

## Changes needed

The {{CHANGE_SOURCES}} below apply to this pass. They take precedence over everything above except the task bodies.

- Re-plan each task they affect. Start from its current plan and change only what they ask for.
- Leave the plans of tasks they don't affect unchanged.
- If they ask for something the task body doesn't allow, say so in the plan. Don't plan outside the task's scope.
- If you can't tell which task they mean, stop and report it.
{{#IF UPSTREAM_CHANGES}}

### Changed since last publish

{{INCLUDE:shared/changed-since-publish.md}}
{{/IF}}
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

{{INCLUDE:shared/design-red-flags.md}}

## Writing a plan

Each plan covers:

- files and modules that will change
- interfaces and call sites
- sequencing and inter-task dependencies
- migration and rollback risk
- test / validation strategy mapped to the task's acceptance criteria
- unresolved decisions, called out explicitly

Don't restate scope, non-goals, dependencies, coverage, or acceptance criteria. The task body already carries them.

## Report back

Name the tasks whose plans you wrote or changed, and those you left unchanged. A missing prerequisite, or a decision only the driver can make, stops the pass: report it exactly and don't guess.
