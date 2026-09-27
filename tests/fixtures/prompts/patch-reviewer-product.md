Judge whether a correction to one already-landed planning artifact affects any artifact built on top of it.

## Execution boundary

You are being invoked as a leaf worker for this one patch impact review.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Do not re-run the calling skill or rediscover the lifecycle stage.

You are strictly read-only: do not edit the work item, its tasks, the draft, or any source file, and do not post comments or run anything that changes state. Read what is supplied, inspect source only when a claim needs it, and return one report to the calling skill.

## Scope

- Work item: 60
- Corrected artifact: Product
- Artifacts to judge, in order: UI, Tasks
- Work in progress on top of them: Technical Plan; ignore it, its owner reconciles it against the corrected text.

## Landed work item body

--- BEGIN LANDED WORK ITEM BODY ---

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

--- END LANDED WORK ITEM BODY ---

## Landed delivery tasks

--- BEGIN LANDED DELIVERY TASKS ---

### WORK-60-TASK-001 — [CORE] First

## Scope
x

## Acceptance criteria
- ok

--- END LANDED DELIVERY TASKS ---

## Corrected Product artifact

This is the reviewed draft that will replace the landed Product artifact above. Compare the two yourself to find what changed.

--- BEGIN PATCHED WORK ITEM BODY ---

## Product

### 4. Functional requirements
- FR-1: The record lands atomically.
- FR-2: The record publishes.

### 5. Constraints
- C-1: Commands own every mutation.

## Decisions
- none

## Open Questions
- none

--- END PATCHED WORK ITEM BODY ---

## What to check

For each artifact to judge, decide whether it still holds against the corrected text: every requirement, constraint, journey, or task body it relies on still says what it assumed, and nothing it states now contradicts the correction. Wording-only changes that leave meaning intact affect nothing. When unsure, name the artifact affected. Your verdict is applied as given: naming a stage returns the work item to it for rework, and `none` lets the work continue on top of the corrected text.

## Report back

Open with exactly one verdict line naming the earliest affected artifact, or `none` when every artifact still holds:

```
Earliest affected stage: <one of UI, Tasks, or none>
```

Then one section per artifact judged, in order, each opening with `Affected` or `Unaffected` and a short justification citing the requirement ids, journeys, or task ids checked:

```
## <artifact>
Unaffected — no journey references FR-4.
```
