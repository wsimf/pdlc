{{UX_DESIGN_LINE}}

Author the `UI` section for this PDLC record and return it as one fragment file.

{{INCLUDE:shared/execution-boundary.md}}
Invoke the UX-design skill named above, if any is named; invoke no other `pdlc-*` skill.
Do not re-run the calling skill or rediscover the lifecycle stage.
Author the fragment directly and return it to the calling skill.

## Parent work item

`{{PARENT_WORK_ITEM}}` — full body:

{{PARENT_BODY}}

## State

- `Status`: UI — `Gate State`: `{{GATE_STATE}}`.
- Why it is Stale (if it is): {{STALE_REASON}}.
- Existing task tree, if any: {{TASK_TREE}}.

## Driver follow-up

{{DRIVER_FOLLOWUP}}

## What to return

One fragment file: the `UI` section — information architecture, interaction
states, loading / error / empty states, accessibility, responsive behaviour, and
every named `UJ-*` journey.

A feature with no user-facing surface still returns a fragment saying so and
why, so applicability is reviewed and approved like any other artifact.

Report whether UI is required. The fragment's own wording is yours to choose;
the calling skill acts on your verdict, not on the prose.
