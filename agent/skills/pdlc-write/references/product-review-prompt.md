# Product-reviewer dispatch prompt

`pdlc-write` Review fills the placeholders below and spawns `pdlc-product-reviewer` with the result, before the specification is landed. Read-only: it returns findings and a verdict, and changes nothing.

---

```md
Review the supplied Product draft before it is posted to the work item store.

## Execution boundary

You are being invoked as the leaf product reviewer.
Do not invoke any `pdlc-*` skill.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Review the supplied draft directly and return one report to the calling `pdlc-write` skill.

## Draft under review

`<exact scratch file path>` — read the whole file; review all of it.

## Current record (reconcile only)

`<complete current work item body, or "none, new record">`

## Prior findings (re-review only)

`<the previous pass's findings, so each can be confirmed addressed — or "none, first review">`

## What to check

- Every cited prior-art path and type exists in current source and does what the draft says.
- Every `FR-*` is behavioural and testable, and every `C-*` is a genuine binding decision.
- Nothing designs UI, breaks work into tasks, or plans implementation.
- When reconciling, nothing quietly contradicts approved product intent the driver did not ask to change.

## Report back

Findings with evidence, coverage boundaries, and exactly one of `Changes Required` or `Approval Required`.
```
