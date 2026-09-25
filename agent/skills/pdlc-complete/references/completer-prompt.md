# Completer dispatch prompt

`pdlc-complete` Dispatch fills the placeholders below and spawns `pdlc-completer`
once with the result. It prepares the structured completion evidence body; it
does not edit the record, does not mutate the work item, and does not complete
anything.

---

```md
Prepare the structured completion evidence body for this PDLC record. Do not
edit the record itself — Product, UI, requirements, and tasks are frozen at
Verification.

## Execution boundary

You are being invoked as a leaf worker for this one bounded task.
Do not invoke any `pdlc-*` skill.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Prepare the evidence body directly and return one report to the calling `pdlc-complete` skill.

## Record

- Complete parent work item body, end to end:

<full body>

- Every task, with its body and `## Implementation` comment:

<one block per task>

- Verification evidence: `<the Verification PDLC-REVIEW report and any deferrals>`.
- Linked PRs and their state: `<numbers, merged/open, check state>`.
- Decisions and Open Questions as they currently stand: `<...>`.
- Upstream patches: `<every PDLC-PATCHED comment, with its time and URL, or "none">`.
- Skipped stages, if any: `<... or "none">`.

## What to return

The completion evidence body only, in the six-section format `pdlc post complete --help` gives.
Decisions come from task implementation notes and the commits that landed them; keep them a compact list, not a second changelog.
List every upstream patch under Decisions: the patched stage, when, a one-line summary naming every requirement it changed, and the comment as reference.
Give one Open Questions line per live entry, with the question verbatim.

Relay judgments plainly. If a live Open Questions entry genuinely cannot be
resolved or deferred, say so — do not invent a disposition to force a clean body.
```
