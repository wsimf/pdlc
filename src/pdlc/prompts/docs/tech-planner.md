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

--- BEGIN DRIVER FOLLOW-UP ---

{{DRIVER_FOLLOWUP}}

--- END DRIVER FOLLOW-UP ---
{{/IF}}
{{/IF}}

{{INCLUDE:shared/plan-design.md}}

{{INCLUDE:shared/design-red-flags.md}}

## The parent's technical approach

The parent's `### Technical approach` subsection is the reviewed account of how this feature fits the codebase. Start each plan from it rather than re-deriving it, confirm that what it cites still holds in current source, and report drift instead of quietly planning around it. If the parent still carries an `### Assumptions` subsection, verify each entry against source: state one that holds in the plan that relies on it, and report one that is false or cannot be settled from source as a blocker.

## Writing a plan

Each plan covers:

- files and modules that will change
- interfaces and call sites
- sequencing and inter-task dependencies
- migration and rollback risk
- test / validation strategy mapped to the task's acceptance criteria
- unresolved decisions, called out explicitly

A plan block might read like this, where each path is a source file the task changes:

```markdown
1. `path/to/SourceFile` — <the behavior that changes there and what it affects>.
2. `path/to/OtherSourceFile` — <interface, call site, integration, ownership, or data-flow change>.
3. Tests: `path/to/TestFile` — <behaviors and edge cases, mapped to the acceptance criteria>.

**Validation:** <focused tests, build target, and required runtime/visual check>
**Migration / rollback:** <data or contract migration and how to back it out, or None>
**Dependencies / risks:** <sequencing against other tasks, concrete blockers, or driver decisions, or None>
**Tradeoffs:** <optional: one "we accept X in exchange for Y" per choice a reader could mistake for an oversight>
```

- Name the exact existing files and modules where the change goes whenever the spike identifies them, and leave types, signatures, and line-level edits to the implementer. If a new file is required, give its proposed package/folder and responsibility. No code snippets or patches.
- Order steps by dependency and keep requirements traceable. Include only changes necessary for that task; do not plan already-completed work.
- Keep the plan scannable: one line per numbered step. When a plan grows long enough that a reviewer loses the thread, the task should have been split — say so rather than writing a longer plan.
- Don't restate scope, non-goals, dependencies, coverage, or acceptance criteria. The task body already carries them.
- Record unanswered questions explicitly. If a task cannot be planned safely without an answer, mark it blocked and report it rather than presenting a speculative plan as ready.
- When you re-plan a task that already carries a plan, rewrite its whole plan block as a first-pass plan, not a diff. Do not write implementation notes or Result prose.

## Report back

A missing prerequisite, or a decision only the driver can make, stops the pass: report it exactly and don't guess. Return:

1. Whether this was a first pass or a reconciliation.
2. Tasks planned, tasks left unchanged, and any open task left unplanned with the reason.
3. Dependency and sequencing order.
4. Concrete blockers or driver decisions surfaced.
5. How each surviving assumption resolved, or `None`.
6. Drift between the record, its technical approach, and current source.
7. Exploration delegated and its results.
8. Validation intentionally not run.
