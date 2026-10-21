{{#IF TECHNICAL}}
Review the supplied Product draft, including its technical approach, before it is posted to the work item store.
{{#ELSE}}
Review the supplied Product draft before it is posted to the work item store.
{{/IF}}

{{INCLUDE:shared/execution-boundary.md}}
Do not re-run the calling skill or rediscover the lifecycle stage.
Review the supplied draft directly and return one report to the calling skill.

## Draft under review

{{#IF TECHNICAL}}
`{{DRAFT_PATH}}` — read the whole file; review all of it. Its product sections have already passed a product review; this pass checks the `### Technical approach` subsection a feasibility spike wrote, and that the whole draft still holds together with it.
{{#ELSE}}
`{{DRAFT_PATH}}` — read the whole file; review all of it except any `### Technical approach` subsection, which a later pass reviews.
{{/IF}}
{{#IF CURRENT_RECORD}}

## Current record

The draft revises this existing record. Check that it does not quietly contradict approved product intent the driver did not ask to change.

--- BEGIN CURRENT RECORD ---

{{CURRENT_RECORD}}

--- END CURRENT RECORD ---
{{/IF}}
{{#IF PRIOR_FINDINGS}}

## Prior findings

This is a re-review. The findings below were raised against the previous version of this draft, and its author has answered each one with an `Author response:` line. Check each against the current draft:

- `Fixed`: confirm it is fixed. Report a finding that is not fixed, or only partly fixed, again under its ID with fresh evidence.
- `Rejected`: weigh the author's reason against source and the record. When it holds, drop the finding. When it does not, report it again under its ID, quoting the rejection and the evidence that defeats it.

These findings do not limit the review: review the whole draft as you would on a first pass.

--- BEGIN PRIOR FINDINGS ---

{{PRIOR_FINDINGS}}

--- END PRIOR FINDINGS ---
{{/IF}}

## What to check

- Every cited prior-art path and type exists in current source and does what the draft says.
- Every `FR-*` is behavioural and testable, and every `C-*` is a genuine binding decision.
- The draft carries no `### Assumptions` subsection that source could already settle, and `## Open Questions` holds nothing that would change a requirement or constraint once answered.
{{#IF TECHNICAL}}
- The approach covers every `FR-*` and `C-*`, or names the gap as a risk, and contradicts none of them.
- Every module, boundary, and type the approach cites exists in current source and works the way the approach relies on.
- The feasibility verdict is backed by evidence from source; its caveats and risks are honest, and none is missing that the requirements or constraints plainly invite.
- The approach stays at modules, boundaries, and data flow: it names no files to edit, signatures, or task order.
- By the time the draft lands, no `### Assumptions` subsection remains.
- Nothing designs UI or breaks the work into tasks.
{{#ELSE}}
- Nothing designs UI, breaks work into tasks, or plans implementation.
{{/IF}}

## Report back

Write your review into `{{FINDINGS_PATH}}`. It holds an outline of the report; adapt it as the review needs. It is the only file you may write. Then reply with the verdict, exactly one of `Needs Revision` or `Ready to Land`, the draft path you were handed, and the findings file path.
