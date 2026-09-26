Author the `UI` section for this PDLC record and return it as one fragment file.

## Execution boundary

You are being invoked as a leaf worker for this one UI section.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
No ux-design skill is configured for this project. Resolve interaction and visual design from the design references named in AGENTS.md and the platform's own conventions.
Do not re-run the calling skill or rediscover the lifecycle stage.
Author the fragment directly and return it to the calling agent.

## Parent work item

Work Item Id: `60`

--- BEGIN PARENT WORK ITEM BODY ---

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

--- END PARENT WORK ITEM BODY ---

## State

- `Status`: UI — `Gate State`: `Stale`.

Existing task tree: - `WORK-60-TASK-001` [CORE] Core work (OPEN).

## Your Task

A previously published UI section, including its `UJ-*` journeys, is in the parent work item above. It was invalidated for this reason:
detail

This is the first rework pass. Revise the published UI section above to address the invalidation reason.

## What to return

One fragment file: the `UI` section — information architecture, interaction states, loading / error / empty states, accessibility, responsive behaviour, and every named `UJ-*` journey.
A feature with no user-facing surface still returns a fragment saying so and why, so applicability is reviewed and approved like any other artifact.
Report whether UI is required. The fragment's own wording is yours to choose; the calling skill acts on your verdict, not on the prose.
