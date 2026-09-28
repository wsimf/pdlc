Review the supplied local artifact before it is written to the work item store.

## Execution boundary

You are being invoked as a leaf worker for this one artifact review.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Do not re-run the calling skill or rediscover the lifecycle stage.
Review the supplied artifact directly and return one report to the calling skill.

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

Review the proposed task breakdown at `$CACHE_ROOT/manifest.json`. Read the manifest and every task file it lists; together they replace the work item's current delivery tasks. Do not edit the manifest or any task file.

Review each task below on its own, then the breakdown as a whole:

- `TASK-001` — untitled (retain): `$CACHE_ROOT/task-001.md`; core, covers FR-1, depends on nothing
- `TASK-002` — Show it (retain): `$CACHE_ROOT/task-002.md`; ui, covers FR-2, UJ-1, depends on TASK-001
- `TASK-003` — WORK-60-TASK-003 [CORE] Export (remove): leaves scope: Folded into TASK-001
- `(new task)` — Retry sync (create): `$CACHE_ROOT/task-004.md`; core, covers FR-1, depends on TASK-001

### Removed tasks

These published tasks leave scope. Confirm each reason holds and that no requirement, journey, or dependency is left uncovered. Their current bodies:

#### `TASK-003` — WORK-60-TASK-003 [CORE] Export

Reason: Folded into TASK-001

--- BEGIN TASK ---

## Scope
x

## Acceptance criteria
- ok

--- END TASK ---

### Prior findings

This is a re-review. The findings below were raised against the previous version of this artifact, and it has been revised since. Check each one against the current files and confirm it is fixed. Report any finding that is not fixed, or only partly fixed, again with fresh evidence. These findings do not limit the review: review the whole artifact as you would on a first pass.

--- BEGIN PRIOR FINDINGS ---

TASK-002 lacks offline criteria

--- END PRIOR FINDINGS ---

## What to check

- Journey and requirement coverage: every task covers at least one FR or C; every UI task covers a `UJ-*`; every `UJ-*` has a UI task; no task claims a requirement the parent does not declare.
- Dependency validity: dependencies exist, the graph is acyclic, ordering is sound.
- Artifact quality: scope, non-goals, acceptance criteria, risk, and HITL/AFK classification are concrete and testable.
- Title clarity: each title reads on its own as a pull request title, saying what changes without the work item.
- Nothing contradicts approved Product or UI intent.

## Report back

Write your review into `$CACHE_ROOT/.pdlc/cache/60/pdlc-tasks-findings.md`. It holds an outline of the report; adapt it as the review needs. It is the only file you may write. Then reply with the verdict, exactly one of `Needs Revision` or `Ready to Land`, the path of the manifest or UI fragment you were handed to review, and the findings file path.
