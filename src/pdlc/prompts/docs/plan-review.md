Review the supplied delivery-task plans before they are posted to the work item store.

{{INCLUDE:shared/execution-boundary.md}}
Do not re-run the calling skill or rediscover the lifecycle stage.
Review the supplied plans directly and return one report to the calling skill.

## Parent work item

{{PARENT_BODY}}

## Plans under review

{{PLANS}}

## Prior findings (re-review only)

{{PRIOR_FINDINGS}}

## What to check

- The plan is actionable: file ownership, interfaces, and sequencing are
  concrete enough to implement from.
- Every acceptance criterion maps to real validation.
- Every spike assumption is resolved, or recorded as an open question.
- No blocking decision is left unanswered.
- Nothing quietly contradicts approved Product or UI intent.

## Report back

Findings with evidence, coverage boundaries, and exactly one of
`Changes Required` or `Approval Required`.
