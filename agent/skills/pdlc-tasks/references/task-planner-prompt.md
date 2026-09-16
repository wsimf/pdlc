# Task-planner dispatch prompt

`pdlc-tasks` Author fills the placeholders below and spawns `pdlc-task-planner`
when `Status = Tasks`. This is also the dispatch you return to in Review with
reviewer findings — keep it addressable.

---

````md
Decompose this PDLC record into a dependency-ordered set of delivery tasks.

## Execution boundary

You are being invoked as the leaf task author.
Do not invoke any `pdlc-*` skill.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Author the breakdown directly and return the task files and manifest to the calling `pdlc-tasks` skill.

## Parent work item

`<number>` — full body, including the `UI` section and every `FR-*` / `C-*` /
`UJ-*` identifier:

<complete parent work item body>

## State

- `Status`: Tasks — `Gate State`: `<Pending | Stale>`.
- Why it is `Stale` (if it is): `<reason, or "n/a — first pass">`.
- Existing task tree, if any — the `# Tasks` blocks verbatim, so each task's
  `completed`, `hasPlan`, and `hasImplementation` are visible. Reconcile against
  it rather than rewriting from scratch: `<...>`.

## Driver follow-up

`<verbatim, or "none">`

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
````
