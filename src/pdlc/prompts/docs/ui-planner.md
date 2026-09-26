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

## State

- `Status`: UI — `Gate State`: `{{GATE_STATE}}`.

{{#IF TASK_TREE}}
Existing task tree: {{TASK_TREE}}.
{{/IF}}

## Your Task

{{#IF STALE_REASON}}
A previously published UI section, including its `UJ-*` journeys, is in the parent work item above. It was invalidated for this reason:
{{STALE_REASON}}

{{#IF DRIVER_FOLLOWUP}}
An unpublished UI revision is at `{{CURRENT_JOURNEYS_PATH}}`. Preserve its fixes for the invalidation reason and apply the driver follow-up below:
{{DRIVER_FOLLOWUP}}
{{#ELSE}}
This is the first rework pass. Revise the published UI section above to address the invalidation reason.
{{/ELSE}}
{{/IF}}
{{#ELSE}}
{{#IF DRIVER_FOLLOWUP}}
An unpublished UI draft is at `{{CURRENT_JOURNEYS_PATH}}`. Revise it to apply the driver follow-up below:
{{DRIVER_FOLLOWUP}}
{{#ELSE}}
We haven't done UI planning before. This is the first time; author the UI section from the parent work item above.
{{/ELSE}}
{{/IF}}
{{/ELSE}}
{{/IF}}

## What to return

One fragment file: the `UI` section — information architecture, interaction states, loading / error / empty states, accessibility, responsive behaviour, and every named `UJ-*` journey.
A feature with no user-facing surface still returns a fragment saying so and why, so applicability is reviewed and approved like any other artifact.
Report whether UI is required. The fragment's own wording is yours to choose; the calling skill acts on your verdict, not on the prose.
