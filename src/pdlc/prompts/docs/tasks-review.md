Review the supplied local artifact before it is written to the work item store.

{{INCLUDE:shared/execution-boundary.md}}
Do not re-run the calling skill or rediscover the lifecycle stage.
Review the supplied artifact directly and return one report to the calling skill.

## Parent work item

{{PARENT_BODY}}

## Artifact under review

{{ARTIFACT}}

## Prior findings (re-review only)

{{PRIOR_FINDINGS}}

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
