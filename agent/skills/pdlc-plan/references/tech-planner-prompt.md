# Technical-planner dispatch prompt

`pdlc-plan` Step 4 fills the placeholders below and spawns `pdlc-tech-planner`
once with the result. This is also the dispatch you return to in Step 6 with
reviewer findings — keep it addressable.

---

````md
Spike the delivery tasks below against current source and return an
implementation-ready plan for each.

## Parent work item

`<number>` — full body:

<complete parent work item body: Product, UI, Decisions, Open Questions>

## Tasks to plan

<for each `needsPlan` task, and any task being reconciled:>

- `<TASK-ID>` (#`<number>`) — `<title>`
  <full task body: scope, non-goals, dependencies, FR/C/UJ coverage, acceptance
  criteria>
  Existing plan (reconciliation only): `<prior `## Technical Plan` text, or
  "none">`

## Driver follow-up

`<the driver's follow-up verbatim, or "none">`

## Constraints and validation

`<relevant source-ownership and architecture constraints; the validation each
task's criteria are expected to map to>`

## What to return

Per task planned, that task's **plan content only — no heading**, covering:

- files and modules that will change
- interfaces and call sites
- sequencing and inter-task dependencies
- migration and rollback risk
- test / validation strategy mapped to the task's acceptance criteria
- any unresolved decision, called out explicitly

`pdlc-post-plan.py` posts this as a standalone `## Technical Plan` comment on the
delivery task and never touches the body, so do not retype scope, non-goals,
dependencies, coverage, or acceptance criteria — they stay exactly as the Tasks
stage authored them.

Return one plan file per task plus a manifest:

```json
[{ "id": "TASK-003", "plan": "/tmp/plan-003.md" }]
```

A pass need not cover every task, but must not leave any open unimplemented task
with no plan at all. A missing prerequisite or a decision only the driver can
make stops the pass — surface it exactly, do not guess an answer.
````
