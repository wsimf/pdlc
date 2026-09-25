# Triage unresolved PR review threads

Use this guide when `pdlc inspect` names an unresolved thread on a registered PR under `# Due Next`.

Read the thread and the current code, its callers, and relevant tests before judging the comment.
Check whether newer commits have already addressed it.
For an actionable production or task-Result issue, write evidence citing the thread URL and the required change, then run `pdlc post triage WORK_ITEM Implementation EVIDENCE_FILE`.
For a test-only or coverage issue, cite the thread and required change and route it to Testing with `pdlc post triage WORK_ITEM Testing EVIDENCE_FILE`.
Follow the owning stage from Changes Required through its usual pipeline, including resolving the thread when the fix is published.

If the thread asks for a product, architecture, UX, safety, or scope decision, stop and take that decision to the driver.
If it is already addressed or needs no action, document why and have the thread resolved on the code host; then re-run `pdlc inspect WORK_ITEM`.
An unresolved thread remains a live signal until it is resolved, so do not claim approval readiness while it stays open.
