# Triage a failed PR check

Use this guide when `pdlc inspect` names a failed check on a registered PR under `# Due Next`.

Read the failed check's log and the PR diff at the checked commit, then reproduce the failure where practical.
Decide whether the failure requires a production or task-Result change, a test or coverage change, or a product, architecture, UX, safety, or scope decision.
Do not classify a red rollup from its name alone; identify the failing assertion or command and the source it exercises.

If the check has turned green and no other live signal remains, re-run `pdlc inspect WORK_ITEM` and follow its current `# Due Next`.
For a production or task-Result fix, write evidence naming the PR, failed check, diagnosis, and Implementation as owner, then run `pdlc post triage WORK_ITEM Implementation EVIDENCE_FILE`.
For a test-only or coverage fix, record the same facts with Testing as owner and run `pdlc post triage WORK_ITEM Testing EVIDENCE_FILE`.
Follow the owning stage from Changes Required through its usual review, CI, and approval gates.

If the diagnosis needs a driver decision, stop and present the evidence and choices to the driver.
Do not use driver-only invalidation to route a CI failure.
