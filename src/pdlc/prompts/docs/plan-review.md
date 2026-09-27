Review the supplied delivery-task plans before they are posted to the work item store.

{{INCLUDE:shared/execution-boundary.md}}
Do not re-run the calling skill or rediscover the lifecycle stage.
Review the supplied plans directly and return one report to the calling skill.

## Work item `{{PARENT_WORK_ITEM}}`

--- BEGIN WORK ITEM ---

{{PARENT_BODY}}

--- END WORK ITEM ---

## Your Task

Review the proposed technical plans in the files the manifest at `{{MANIFEST_PATH}}` names. Each file holds the task body between `--- BEGIN TASK ---` and `--- END TASK ---`, then the proposed plan between `--- BEGIN TECH PLAN ---` and `--- END TECH PLAN ---`. Read every file in full and review each plan against its task body and the work item above.

Do not edit the manifest or any task file. Only files left exactly as they were handed to you can land; an edit is undone and this review discarded.

{{#EACH TASKS}}
- `{{TASK_ID}}` — {{TASK_TITLE}} ({{TASK_CHANGE}}): `{{TASK_FILE}}`
{{/EACH}}
{{#IF REPLACED_PLANS}}

### Recorded plans being replaced

These tasks already carry a recorded plan that the proposed one replaces. Confirm each replacement is warranted and drops nothing the recorded plan got right.
{{#EACH REPLACED_PLANS}}

#### `{{TASK_ID}}` — {{TASK_TITLE}}

--- BEGIN RECORDED PLAN ---

{{RECORDED_PLAN}}

--- END RECORDED PLAN ---
{{/EACH}}
{{/IF}}
{{#IF PRIOR_FINDINGS}}

### Prior findings

This is a re-review. The findings below were raised against the previous version of these plans, and they have been revised since. Check each one against the current files and confirm it is fixed. Report any finding that is not fixed, or only partly fixed, again with fresh evidence. These findings do not limit the review: review every plan as you would on a first pass.

--- BEGIN PRIOR FINDINGS ---

{{PRIOR_FINDINGS}}

--- END PRIOR FINDINGS ---
{{/IF}}

## What to check

- The plan is actionable: file ownership, interfaces, and sequencing are concrete enough to implement from.
- Every acceptance criterion maps to real validation.
- Every spike assumption is resolved, or recorded as an open question.
- No blocking decision is left unanswered.
- Nothing quietly contradicts approved Product or UI intent.

## Report back

Write your review into `{{FINDINGS_PATH}}`. It holds an outline of the report; adapt it as the review needs. It is the only file you may write. Then reply with the verdict, exactly one of `Needs Revision` or `Ready to Land`, the path of the manifest you were handed to review, and the findings file path.
