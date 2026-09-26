Break this work item into the smallest dependency-ordered set of independently verifiable delivery tasks.

{{INCLUDE:shared/execution-boundary.md}}
Work from this brief. Author the breakdown and return the task files and manifest to the calling agent.

## Work item `{{PARENT_WORK_ITEM}}`

--- BEGIN WORK ITEM ---

{{PARENT_BODY}}

--- END WORK ITEM ---

## Your Task

{{#IF STALE_REASON}}
The published Tasks stage was invalidated for this reason:

{{STALE_REASON}}

{{#IF CURRENT_TASKS_MANIFEST_PATH}}
An unpublished revision is described by the manifest at `{{CURRENT_TASKS_MANIFEST_PATH}}`. Read the manifest and each task body it references, use that revision as the starting breakdown, and preserve its fixes for the invalidation reason.
{{#ELSE}}
This is the first rework pass. Reconcile any existing tasks below to address the invalidation reason.
{{/ELSE}}
{{/IF}}
{{#ELSE}}
{{#IF CURRENT_TASKS_MANIFEST_PATH}}
An unpublished task breakdown is described by the manifest at `{{CURRENT_TASKS_MANIFEST_PATH}}`. Read the manifest and each task body it references, and use that revision as the starting breakdown.
{{#ELSE}}
{{#IF EXISTING_TASKS}}
The published task breakdown is included below. Reconcile it against the current work item.
{{#ELSE}}
We haven't planned delivery tasks before. This is the first breakdown; decompose the work item above.
{{/ELSE}}
{{/IF}}
{{/ELSE}}
{{/IF}}
{{/ELSE}}
{{/IF}}
{{#IF CHANGE_SOURCES}}

Reconcile the {{CHANGE_SOURCES}} below against the work item; the work item remains the contract. Apply each change to the tasks it affects. If a change conflicts with the work item or cannot be mapped to a task or requirement, stop and report it.
{{#IF CHANGE_REQUESTS}}

### Change requests

Findings recorded against this stage since it last published.

--- BEGIN CHANGE REQUESTS ---

{{CHANGE_REQUESTS}}

--- END CHANGE REQUESTS ---
{{/IF}}
{{#IF DRIVER_FOLLOWUP}}

### Driver follow-up

A change the driver asked for, or findings from a review of the breakdown, verbatim.

{{DRIVER_FOLLOWUP}}
{{/IF}}
{{/IF}}
{{#IF EXISTING_TASKS}}

## Existing tasks

Reconcile this complete breakdown against the current work item.

- Rewrite, add, or remove only tasks affected by the current work item or the changes.
- Carry every unaffected existing task in the manifest with `"unchanged": true`; return no body for it.
- Preserve complete requirement, journey, and dependency coverage across the resulting tree.
{{#EACH EXISTING_TASKS}}

### `{{TASK_ID}}`

{{TASK_METADATA}}

--- BEGIN TASK BODY ---

{{TASK_BODY}}

--- END TASK BODY ---
{{/EACH}}
{{/IF}}

{{INCLUDE:shared/task-sequencing.md}}

## Return

Return one body file for each new or rewritten task, plus a manifest:

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
- Carry every unaffected existing task forward with `{"id": "TASK-002",
  "unchanged": true, "ui": false, "covers": [...], "depends": [...]}` — no
  `title`, no `body`. It stays in the breakdown and its coverage still counts,
  but nothing about it is rewritten and no later stage revisits it.
- Supplying a `title` or `body` for a task whose work already landed rewrites
  it: a rewritten task that was closed is reopened and its plan and
  implementation evidence retired, so it is planned and built again. Do that
  only when the current work item or changes genuinely require it.
- `covers` / `depends` are machine-checked against the parent's own identifiers
  and against the graph — they must match what each task body actually says.

Each task body carries scope, non-goals, dependency links, FR/C/UJ coverage,
HITL/AFK classification, acceptance criteria, risk, and expected implementation
evidence. Every task covers at least one FR or C; every UI task covers a `UJ-*`
and every `UJ-*` has a UI task.
