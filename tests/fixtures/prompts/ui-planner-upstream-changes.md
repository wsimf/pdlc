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

## Decisions
- none

## Open Questions
- none

--- END PARENT WORK ITEM BODY ---

## State

- `Status`: UI — `Gate State`: `Stale`.

Existing task tree: - `WORK-60-TASK-001` [CORE] Core work (OPEN).

## Your Task

Revise the UI section at `$CACHE_ROOT/.pdlc/cache/60/pdlc-ui-planner-fragment.md`. Read it, then edit it in place against the work item and any inputs below, preserving journeys and decisions they do not affect. Return this file.

### Invalidation reason

The published UI stage was invalidated for this reason. Reconcile the section against it.

Returned by a patch of Product; impact A

### Changed since last publish

Upstream stages changed after this stage last published. The work item already reflects them. Use them to find which parts of the existing work they affect and update those; leave the rest unchanged.

--- BEGIN UPSTREAM CHANGES ---

### Patch — 2026-06-03 00:00 UTC

Patched stage: Product
Active stage: Tasks / Pending
Returned to: UI / Stale

impact A

--- END UPSTREAM CHANGES ---

### Change requests

Findings recorded against this stage since it last published. Reconcile them against the work item; the work item remains the contract. Apply each change to the journeys it affects. If a change conflicts with the work item, stop and report it.

--- BEGIN CHANGE REQUESTS ---

### Change request — 2026-06-04 00:00 UTC

Invalidated stage: UI

Returned by a patch of Product; impact A

--- END CHANGE REQUESTS ---

## What to return

One fragment file: the `UI` section — information architecture, interaction states, loading / error / empty states, accessibility, responsive behaviour, and every named `UJ-*` journey.
A feature with no user-facing surface still returns a fragment saying so and why, so applicability is reviewed and approved like any other artifact.
Report whether UI is required. The fragment's own wording is yours to choose; the calling skill acts on your verdict, not on the prose.
