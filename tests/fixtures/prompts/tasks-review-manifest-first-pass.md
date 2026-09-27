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

- `TASK-001` — Core work (create): `$CACHE_ROOT/task-001.md`; core, covers FR-1, depends on nothing
- `TASK-002` — Show it (create): `$CACHE_ROOT/task-002.md`; ui, covers FR-2, UJ-1, depends on TASK-001

## What to check

- Journey and requirement coverage: every task covers at least one FR or C; every UI task covers a `UJ-*`; every `UJ-*` has a UI task; no task claims a requirement the parent does not declare.
- Dependency validity: dependencies exist, the graph is acyclic, ordering is sound.
- Artifact quality: scope, non-goals, acceptance criteria, risk, and HITL/AFK classification are concrete and testable.
- Nothing contradicts approved Product or UI intent.

## Report back

Write your review into `$CACHE_ROOT/.pdlc/cache/60/pdlc-tasks-findings.md`. It holds an outline of the report; adapt it as the review needs. It is the only file you may write. Then reply with the verdict, exactly one of `Changes Required` or `Approval Required`, the files you reviewed, and that file's path.
