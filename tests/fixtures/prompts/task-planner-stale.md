Decompose this PDLC record into a dependency-ordered set of delivery tasks.

## Execution boundary

You are being invoked as a leaf worker for this one breakdown.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Do not re-run the calling skill or rediscover the lifecycle stage.
Author the breakdown directly and return the task files and manifest to the
calling skill.

## Parent work item

`60` — full body, including the `UI` section and every
`FR-*` / `C-*` / `UJ-*` identifier:

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


## State

- `Status`: Tasks — `Gate State`: `Stale`.
- Why it is `Stale` (if it is): ### Change request — 2026-04-01 00:00 UTC

Invalidated stage: Tasks
detail
- Existing task tree, if any — the `# Tasks` blocks verbatim, so each task's
  `completed`, `hasPlan`, and `hasImplementation` are visible. Reconcile
  against it rather than rewriting from scratch:

---
number: 601
title: "WORK-60-TASK-001 [CORE] Core work"
completed: false
isUI: false
hasPlan: false
hasImplementation: false
implementationInvalidated: false
needsPlan: true
---

## Driver follow-up

none

## Sequencing the tasks

Tasks land in order, each on its own pull request stacked on the one before, so
the order of the tree is the order a reviewer reads the change. Sequence it so
the stack proves itself.

- **Each task ends in a state you can check.** Its acceptance criteria hold on
  its own pull request, before any later task lands. A criterion only a later
  task can satisfy belongs to that later task.
- **Scaffold first.** A contract every later task consumes — a shared model, a
  boundary, an error vocabulary — lands in the earliest task that needs it, not
  re-described across several. Ask of each early task: does every task after it
  benefit from this existing?
- **Each task lands one coherent capability** or deepens one that already
  exists. Do not spread a capability across tasks as special-case pieces that
  only work once all of them land.
- **Subtract before you add.** When the requirements replace existing
  behaviour, retiring the old behaviour is part of the tree, not a follow-up:
  order the removal first when it simplifies what follows, or put it in the same
  task as its replacement. Never leave a tree that ships the old and new paths
  side by side.
- **Migrate, then delete.** When a requirement moves callers to a new contract,
  the same wave moves every caller and removes the old contract. A compatibility
  path survives only when a requirement or constraint names an external
  consumer that needs it.

## What to return

One body file per task, plus a manifest:

```json
[
  {
    "id": "TASK-001",
    "title": "Persist route profile geometry",
    "body": "/tmp/task-001.md",
    "ui": false,
    "covers": ["FR-2", "C-1"],
    "depends": []
  }
]
```

- `title` is human-readable only — the script composes the stable
  `WORK-<parent>-TASK-<nnn>` identity and stamps the `[UI]` / `[CORE]` tag from
  `ui`, so `ui` must be a strict, accurate `true` / `false`.
- `id` is optional: supply it to update an existing task, omit it for a new one
  (the script assigns the next number).
- Preserve settled or implemented task scope unless the parent's requirements
  actually changed it. Carry such a task forward with `{"id": "TASK-002",
  "unchanged": true, "ui": false, "covers": [...], "depends": [...]}` — no
  `title`, no `body`. It stays in the breakdown and its coverage still counts,
  but nothing about it is rewritten and no later stage revisits it.
- Supplying a `title` or `body` for a task whose work already landed rewrites
  it: a rewritten task that was closed is reopened and its plan and
  implementation evidence retired, so it is planned and built again. Do that
  only when the requirements moved and the task genuinely has to change.
- `covers` / `depends` are machine-checked against the parent's own identifiers
  and against the graph — they must match what each task body actually says.

Each task body carries scope, non-goals, dependency links, FR/C/UJ coverage,
HITL/AFK classification, acceptance criteria, risk, and expected implementation
evidence. Every task covers at least one FR or C; every UI task covers a `UJ-*`
and every `UJ-*` has a UI task.
