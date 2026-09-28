Author the `UI` section for this PDLC record and return it as one fragment file.

{{INCLUDE:shared/execution-boundary.md}}
{{UX_DESIGN_LINE}}
Do not re-run the calling skill or rediscover the lifecycle stage.
Author the fragment directly and return it to the calling agent.

## Parent work item

Work Item Id: `{{PARENT_WORK_ITEM}}`

--- BEGIN PARENT WORK ITEM BODY ---

{{PARENT_BODY}}

--- END PARENT WORK ITEM BODY ---

{{#IF ATTACHMENTS}}
{{INCLUDE:shared/attachments.md}}

{{/IF}}
## State

- `Status`: UI — `Gate State`: `{{GATE_STATE}}`.

{{#IF TASK_TREE}}
Existing task tree: {{TASK_TREE}}.
{{/IF}}

## Your Task

{{#IF FRAGMENT_PATH}}
Revise the UI section at `{{FRAGMENT_PATH}}`. Read it, then edit it in place against the work item and any inputs below, preserving journeys and decisions they do not affect. Return this file.
{{#ELSE}}
No UI section exists yet. Author it from the parent work item above.
{{/IF}}
{{#IF STALE_REASON}}

### Invalidation reason

The published UI stage was invalidated for this reason. Reconcile the section against it.

--- BEGIN INVALIDATION REASON ---

{{STALE_REASON}}

--- END INVALIDATION REASON ---
{{/IF}}
{{#IF UPSTREAM_CHANGES}}

### Changed since last publish

{{INCLUDE:shared/changed-since-publish.md}}
{{/IF}}
{{#IF CHANGE_REQUESTS}}

### Change requests

Findings recorded against this stage since it last published. Reconcile them against the work item; the work item remains the contract. Apply each change to the journeys it affects. If a change conflicts with the work item, stop and report it.

--- BEGIN CHANGE REQUESTS ---

{{CHANGE_REQUESTS}}

--- END CHANGE REQUESTS ---
{{/IF}}
{{#IF DRIVER_FOLLOWUP}}

### Driver follow-up

A change the driver asked for, or findings from a review of the section, verbatim. Apply it to the journeys it affects; if it conflicts with the work item, stop and report it.

--- BEGIN DRIVER FOLLOW-UP ---

{{DRIVER_FOLLOWUP}}

--- END DRIVER FOLLOW-UP ---
{{/IF}}

## What to return

One fragment file: the `UI` section — information architecture, interaction states, loading / error / empty states, accessibility, responsive behaviour, and every named `UJ-*` journey.
A feature with no user-facing surface still returns a fragment saying so and why, so applicability is reviewed and approved like any other artifact.
Report whether UI is required. The fragment's own wording is yours to choose; the calling skill acts on your verdict, not on the prose.
