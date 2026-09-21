Spike the delivery tasks below against current source and return an
implementation-ready plan for each.

## Execution boundary

You are being invoked as a leaf worker for this one planning pass.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Bounded, read-only codebase exploration is the only delegation allowed.
Do not re-run the calling skill or rediscover the lifecycle stage.
Author the plans directly and return the plan files and manifest to the
calling skill.

## Parent work item

`60` — full body, including the `UI` section, Decisions, and
Open Questions:

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


## Tasks to plan

Every open, unimplemented task, lowest first. Plan each task marked as needing
a plan. Re-plan a task that already carries one only when the recorded evidence
or the driver follow-up sends it back; otherwise leave it alone.

### `WORK-60-TASK-001` [CORE] Core work (#601)

Needs a plan: no — already planned

## Scope
Build the seam.

Covers FR-1.

## Acceptance criteria
- it works

Existing plan:

Touch one module.

### `WORK-60-TASK-002` [UI] Second (#602)

Needs a plan: yes

## Scope
Show it.

Covers FR-2, UJ-1.

## Acceptance criteria
- it shows

Existing plan:

none recorded

## Recorded evidence

### Change request — 2026-04-01 00:00 UTC

Invalidated stage: Technical Plan
detail

## Driver follow-up

re-spike TASK-001 against the cache

## Shape of the change

Make the smallest change that satisfies the task, and leave the code you touch
simpler than you found it. Removals stay inside the files this task owns —
anything wider is a line in your report, not a change.

- Subtract before you add. Dead code, a stub, a redundant validator, or a
  decision duplicated across the files you are touching goes first; build on
  the smaller base.
- Fewer lines beat elegant boilerplate. A wrapper, layer, or abstraction with
  one caller is not worth its indirection.
- Do not repeat a decision in several places. Put it behind one source of truth
  and pass the result.
- Do not thread a new signal through types, schemas, or pipelines when a direct
  path exists. Where the plan asks for the threading, follow the plan and say
  in your report where the direct path would have done.
- When this task replaces an internal API, migrate its callers and delete the
  old one here. A compatibility shim kept only because internal callers still
  exist is dual-path complexity, not a migration.
- If answering a question about this code takes tracing through more than about
  three files, the shape is wrong.

Types and boundaries:

- Make illegal states unrepresentable. Model variants as a sum type rather than
  a bag of optional fields whose contradictory combinations still compile. If
  you could write a comment explaining which combinations are valid, the type
  is too loose.
- Give distinct meanings distinct types. Two parameters that share a primitive
  type and mean different things should not be interchangeable.
- Parse external data at the boundary — CLI arguments, config, network
  payloads, stored rows — into the typed model, then trust the types inside. A
  nil check deep in a call chain the boundary already covered is noise.
- Do not lie to the compiler. A cast, force-unwrap, or assertion that bypasses
  a fact you cannot prove is a runtime failure in waiting: prove it, model it
  away, or report that you could not.
- Match on a variant exhaustively, so a variant added later fails the build
  instead of falling through silently.

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
