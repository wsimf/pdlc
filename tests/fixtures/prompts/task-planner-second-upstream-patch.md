Break this work item into the smallest dependency-ordered set of independently verifiable delivery tasks.

## Execution boundary

You are being invoked as a leaf worker for this one breakdown.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Work from this brief. Author the breakdown and return the task files and manifest to the calling agent.

## Work item `60`

--- BEGIN WORK ITEM ---

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

--- END WORK ITEM ---

## Your Task

Revise the task breakdown at `$CACHE_ROOT/.pdlc/cache/60/pdlc-task-planner-manifest.json`. Read its manifest and task files, then edit them in place against the work item and any inputs below.

### Changed since last publish

Upstream stages changed after this stage last published. The work item already reflects them. Use them to find which parts of the existing work they affect and update those; leave the rest unchanged.

--- BEGIN UPSTREAM CHANGES ---

### Patch — 2026-06-12 00:00 UTC

Patched stage: Product
Active stage: Technical Plan / Pending
Returned to: UI / Stale

impact B

### Invalidation — 2026-06-13 00:00 UTC

Invalidated stage: UI

Returned by a patch of Product; impact B

--- END UPSTREAM CHANGES ---

## Existing tasks

The manifest above carries the complete editable breakdown. These titles identify its published tasks:

- `TASK-001` — [CORE] Core work (open, unplanned, unimplemented)

Rewrite or add only tasks affected by the work item or changes. Keep unaffected tasks as `"action": "retain"` without editing their files. If a task must leave scope, set `"action": "remove"` and give a reason. Preserve complete requirement, journey, and dependency coverage across the resulting tree.

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

## Return

Return the revised manifest and its task files. For a first breakdown, create both:

```json
[
  {
    "action": "create",
    "title": "Persist route profile geometry",
    "body": "/tmp/task-001.md",
    "type": "core",
    "covers": ["FR-2", "C-1"],
    "depends": []
  }
]
```

- `create` adds a task; omit `action` and `id` for the next free number, or supply a new `TASK-NNN` id with `"action": "create"`.
- `retain` keeps an existing task. Keep its generated fields and body path; the command compares its content with the stored task and updates it only when it changed. A changed closed task reopens for planning and implementation.
- `remove` descopes an existing, unimplemented task. Keep its generated `id`, `number`, and `baseline`, add a nonempty `reason`, and remove title, body, type, covers, and depends. A task with a registered pull request cannot be removed.
- `title` is the human-readable half only. The command composes the stable identity and stamps `[UI]` or `[CORE]` from `type`. It also becomes the task's pull request title, so write it for someone who has not read the work item: one short imperative sentence naming the capability or change and where it lands, with no task or requirement IDs and no unexplained feature jargon — "Persist route profile geometry", not "Implement FR-2" or "Backend changes".
- `covers` and `depends` must agree with each task body and the parent work item. The command validates coverage and the dependency graph.

Each task body carries dependency links, FR/C/UJ coverage, scope, and acceptance criteria. Include non-goals, risk, or expected implementation evidence only when useful. Every task covers at least one FR or C; every UI task covers a `UJ-*` and every `UJ-*` has a UI task.
