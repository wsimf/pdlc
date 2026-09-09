# Plan-reviewer dispatch prompt

`pdlc-plan` Step 6 fills the placeholders below and spawns `pdlc-plan-reviewer`
with the result, before any plan is landed. Read-only: it returns findings and a
verdict, and changes nothing.

---

```md
Review the supplied delivery-task plans before they are posted to the work item store.

## Execution boundary

You are being invoked as the leaf plan reviewer.
Do not invoke any `pdlc-*` skill.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Review the supplied plans directly and return one report to the calling `pdlc-plan` skill.

## Parent work item

<complete parent work item body: Product, UI, Decisions, Open Questions>

## Plans under review

<for each entry in the manifest:>

- `<TASK-ID>` — current task body (plus any existing `## Technical Plan`
  comment): `<...>`
  Proposed plan: `<full plan file contents>`

## Prior findings (re-review only)

`<the previous pass's findings, so each can be confirmed addressed — or "none,
first review">`

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
```
