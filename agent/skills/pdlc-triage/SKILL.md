---
name: pdlc-triage
description: "Investigate live registered-PR CI failures and unresolved review threads named by pdlc inspect, route actionable delivery rework, and return to the normal PDLC pipeline."
argument-hint: "Parent work item number to triage"
---

# Triage live PR signals

Run `pdlc inspect WORK_ITEM` and use its current `# Due Next` as the signal list.
Read `pdlc guide triage-ci-failure` for each failed check and `pdlc guide triage-pr-review` for each unresolved thread listed there.
Investigate every listed signal against current source and check logs; a signal's presence does not establish its fix owner.

When a fix is clear, record the diagnosis and signal reference in an evidence file, then run `pdlc post triage WORK_ITEM TARGET EVIDENCE_FILE` with the earliest owning target: Implementation for production or task-Result work, Testing for test-only or coverage work.
If signals require both, choose Implementation first and record both; Testing follows in the normal pipeline.
The command must return `gateState: Changes Required`; report that result so the controller re-polls and dispatches the owning stage's normal work.

If a signal no longer exists, re-run `pdlc inspect WORK_ITEM` and follow its current route.
If a comment needs no change, ensure its code-host thread is resolved before proceeding; if it cannot be resolved, report the blocker.
Stop for a driver decision when triage cannot determine the scope or product intent.
Do not run `pdlc post invalidate`.
