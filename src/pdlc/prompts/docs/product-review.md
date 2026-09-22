Review the supplied Product draft before it is posted to the work item store.

{{INCLUDE:shared/execution-boundary.md}}
Do not re-run the calling skill or rediscover the lifecycle stage.
Review the supplied draft directly and return one report to the calling skill.

## Draft under review

`{{DRAFT_PATH}}` — read the whole file; review all of it.

## Current record (reconcile only)

{{CURRENT_RECORD}}

## Prior findings (re-review only)

{{PRIOR_FINDINGS}}

## What to check

- Every cited prior-art path and type exists in current source and does what the draft says.
- Every `FR-*` is behavioural and testable, and every `C-*` is a genuine binding decision.
- Nothing designs UI, breaks work into tasks, or plans implementation.
- When reconciling, nothing quietly contradicts approved product intent the driver did not ask to change.

## Report back

Findings with evidence, coverage boundaries, and exactly one of `Changes Required` or `Approval Required`.
