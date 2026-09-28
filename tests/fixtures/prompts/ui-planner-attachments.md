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

## Attachments

Files attached to the work item, such as mockups or screenshots. Read the ones that inform your task. Where a Figma or other mockup covers a UI journey, follow that design as closely as possible.

1. Primary navigation mockup
  - Path: $PDLC_HOME/60/attachments/att_4597f8b310a1c49556df76c44c94a7b40c1e04d4b7b015c54519b4b30457bffa.png
2. att_8902eec15e01d879d27e127f86f0ea271626438e4f0552b69d6200254371fb0f.png
  - Path: $PDLC_HOME/60/attachments/att_8902eec15e01d879d27e127f86f0ea271626438e4f0552b69d6200254371fb0f.png

## State

- `Status`: UI — `Gate State`: `Pending`.


## Your Task

No UI section exists yet. Author it from the parent work item above.

## What to return

One fragment file: the `UI` section — information architecture, interaction states, loading / error / empty states, accessibility, responsive behaviour, and every named `UJ-*` journey.
A feature with no user-facing surface still returns a fragment saying so and why, so applicability is reviewed and approved like any other artifact.
Report whether UI is required. The fragment's own wording is yours to choose; the calling skill acts on your verdict, not on the prose.
