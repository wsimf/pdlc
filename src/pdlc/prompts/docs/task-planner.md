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
An unpublished revision is at `{{CURRENT_TASKS_MANIFEST_PATH}}`. Read its manifest and task files, revise that breakdown, and preserve its fixes for the invalidation reason.
{{#ELSE}}
This is the first rework pass. An editable copy of the published breakdown is at `{{STARTING_MANIFEST_PATH}}`. Read its manifest and task files, then revise it to address the invalidation reason.
{{/ELSE}}
{{/IF}}
{{#ELSE}}
{{#IF CURRENT_TASKS_MANIFEST_PATH}}
An unpublished task breakdown is at `{{CURRENT_TASKS_MANIFEST_PATH}}`. Read its manifest and task files, then revise that breakdown.
{{#ELSE}}
{{#IF EXISTING_TASKS}}
An editable copy of the published breakdown is at `{{STARTING_MANIFEST_PATH}}`. Read its manifest and task files, then reconcile it against the current work item.
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

The manifest above carries the complete editable breakdown. These titles identify its published tasks:

{{#EACH EXISTING_TASKS}}
- `{{TASK_ID}}` — {{TASK_TITLE}} ({{TASK_PROGRESS}})
{{/EACH}}

Rewrite or add only tasks affected by the work item or changes. Keep unaffected tasks as `"action": "retain"` without editing their files. If a task must leave scope, set `"action": "remove"` and give a reason. Preserve complete requirement, journey, and dependency coverage across the resulting tree.
{{/IF}}

{{INCLUDE:shared/task-sequencing.md}}

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
- `title` is the human-readable half only. The command composes the stable identity and stamps `[UI]` or `[CORE]` from `type`.
- `covers` and `depends` must agree with each task body and the parent work item. The command validates coverage and the dependency graph.

Each task body carries scope, non-goals, dependency links, FR/C/UJ coverage,
HITL/AFK classification, acceptance criteria, risk, and expected implementation
evidence. Every task covers at least one FR or C; every UI task covers a `UJ-*`
and every `UJ-*` has a UI task.
