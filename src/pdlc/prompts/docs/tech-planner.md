Spike the delivery tasks below against current source and return an
implementation-ready plan for each.

{{INCLUDE:shared/execution-boundary.md}}
Bounded, read-only codebase exploration is the only delegation allowed.
Do not re-run the calling skill or rediscover the lifecycle stage.
Author the plans directly and return the plan files and manifest to the
calling skill.

## Parent work item

`{{PARENT_WORK_ITEM}}` — full body, including the `UI` section, Decisions, and
Open Questions:

{{PARENT_BODY}}

## Tasks to plan

Every open, unimplemented task, lowest first. Plan each task marked as needing
a plan. Re-plan a task that already carries one only when the recorded evidence
or the driver follow-up sends it back; otherwise leave it alone.

{{#EACH TASKS}}
### `{{TASK_TAG}}` {{TASK_TITLE}} (#{{TASK_NUMBER}})

Needs a plan: {{NEEDS_PLAN}}

{{TASK_BODY}}

Existing plan:

{{TECHNICAL_PLAN}}

{{/EACH}}
## Recorded evidence

{{EVIDENCE}}

## Driver follow-up

{{DRIVER_FOLLOWUP}}

{{INCLUDE:shared/change-shape.md}}

The implementer who carries out each plan is held to the rules above. Plan a
change they can follow without breaking one: where a rule and the task pull
apart, say so in the plan rather than planning around it.

## What to return

Per task planned, that task's **plan content only — no heading**, covering:

- files and modules that will change
- interfaces and call sites
- sequencing and inter-task dependencies
- migration and rollback risk
- test / validation strategy mapped to the task's acceptance criteria
- any unresolved decision, called out explicitly

Each plan is posted as a standalone `## Technical Plan` comment on its delivery
task and never touches the body, so do not retype scope, non-goals,
dependencies, coverage, or acceptance criteria — they stay exactly as the task
body states them.

Return one plan file per task plus a manifest:

```json
[{ "id": "TASK-003", "plan": "/tmp/plan-003.md" }]
```

A pass need not cover every task, but must not leave any open unimplemented task
with no plan at all. A missing prerequisite or a decision only the driver can
make stops the pass — surface it exactly, do not guess an answer.
