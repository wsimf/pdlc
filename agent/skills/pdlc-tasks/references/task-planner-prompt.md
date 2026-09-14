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
- Existing task tree, if any — reconcile against it rather than rewriting from
  scratch: `<...>`.

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
- `covers` / `depends` are machine-checked against the parent's own identifiers
  and against the graph — they must match what each task body actually says.

Each task body carries scope, non-goals, dependency links, FR/C/UJ coverage,
HITL/AFK classification, acceptance criteria, risk, and expected implementation
evidence. Every task covers at least one FR or C; every UI task covers a `UJ-*`
and every `UJ-*` has a UI task.
````
