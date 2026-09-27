Review the supplied local artifact before it is written to the work item store.

## Execution boundary

You are being invoked as a leaf worker for this one artifact review.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Do not re-run the calling skill or rediscover the lifecycle stage.
Review the supplied artifact directly and return one report to the calling skill.

## Parent work item

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

## Artifact under review

**UI Phase:** Required.

### UJ-1 — Land the record

Draft journey.

## Prior findings (re-review only)

none, first review

## What to check

- Journey and requirement coverage: every task covers at least one FR or C;
  every UI task covers a `UJ-*`; every `UJ-*` has a UI task; no task claims a
  requirement the parent does not declare.
- Dependency validity: dependencies exist, the graph is acyclic, ordering is
  sound.
- Artifact quality: scope, non-goals, acceptance criteria, risk, and HITL/AFK
  classification are concrete and testable; no empty detail block.
- No delivery task carries a `## Technical Plan` or `## Implementation` comment — the
  Tasks stage precedes both.
- Nothing contradicts approved Product or UI intent.

## Report back

Findings with evidence, coverage boundaries, and exactly one of `Clean` or
`Changes`.
