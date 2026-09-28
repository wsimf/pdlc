Review the supplied Product draft before it is posted to the work item store.

{{INCLUDE:shared/execution-boundary.md}}
Do not re-run the calling skill or rediscover the lifecycle stage.
Review the supplied draft directly and return one report to the calling skill.

## Draft under review

`{{DRAFT_PATH}}` — read the whole file; review all of it.
{{#IF CURRENT_RECORD}}

## Current record

The draft revises this existing record. Check that it does not quietly contradict approved product intent the driver did not ask to change.

--- BEGIN CURRENT RECORD ---

{{CURRENT_RECORD}}

--- END CURRENT RECORD ---
{{/IF}}
{{#IF PRIOR_FINDINGS}}

## Prior findings

This is a re-review. The findings below were raised against the previous version of this draft, and it has been revised since. Check each one against the current draft and confirm it is fixed. Report any finding that is not fixed, or only partly fixed, again with fresh evidence. These findings do not limit the review: review the whole draft as you would on a first pass.

--- BEGIN PRIOR FINDINGS ---

{{PRIOR_FINDINGS}}

--- END PRIOR FINDINGS ---
{{/IF}}

## What to check

- Every cited prior-art path and type exists in current source and does what the draft says.
- Every `FR-*` is behavioural and testable, and every `C-*` is a genuine binding decision.
- Nothing designs UI, breaks work into tasks, or plans implementation.

## Report back

Findings with evidence, coverage boundaries, and exactly one of `Changes Required` or `Approval Required`.
