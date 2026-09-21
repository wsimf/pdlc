Decompose this PDLC record into a dependency-ordered set of delivery tasks.

{{INCLUDE:shared/execution-boundary.md}}
Do not re-run the calling skill or rediscover the lifecycle stage.
Author the breakdown directly and return the task files and manifest to the
calling skill.

## Parent work item

`{{PARENT_WORK_ITEM}}` — full body, including the `UI` section and every
`FR-*` / `C-*` / `UJ-*` identifier:

{{PARENT_BODY}}

## State

- `Status`: Tasks — `Gate State`: `{{GATE_STATE}}`.
- Why it is `Stale` (if it is): {{STALE_REASON}}
- Existing task tree, if any — the `# Tasks` blocks verbatim, so each task's
  `completed`, `hasPlan`, and `hasImplementation` are visible. Reconcile
  against it rather than rewriting from scratch:

{{EXISTING_TASKS}}

## Driver follow-up

{{DRIVER_FOLLOWUP}}

{{INCLUDE:shared/task-sequencing.md}}

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
