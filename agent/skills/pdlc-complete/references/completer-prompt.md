# Completer dispatch prompt

`pdlc-complete` Step 2 fills the placeholders below and spawns `pdlc-completer`
once with the result. It prepares the structured completion evidence body; it
does not edit the record, does not mutate the work item, and does not complete
anything.

---

```md
Prepare the structured completion evidence body for this PDLC record. Do not
edit the record itself — Product, UI, requirements, and tasks are frozen at
Verification.

## Record

- Complete parent work item body, end to end:

<full body>

- Every task, with its body and `## Implementation` comment:

<one block per task>

- Verification evidence: `<the Verification PDLC-REVIEW report and any deferrals>`.
- Linked PRs and their state: `<numbers, merged/open, check state>`.
- Decisions and Open Questions as they currently stand: `<...>`.
- Skipped stages, if any: `<... or "none">`.

## What to return

The completion evidence body only, with all six `##` sections:

```md
## Shipped

<scope delivered — tasks, PRs, what a user can now do>

## Verification

clean @ <commit> — <one-line summary of the verification outcome>

## Decisions

- <decision that emerged during delivery> — <rationale> (<task or PR ref>)
  (or a lone "- None"; read from task implementation notes and the commits that
  landed them; compact list, not a second changelog)

## Open Questions

- <live question, verbatim from the record> — Resolved: <answer>
- <live question> — Deferred: <what>, tracked as <follow-up record or reason>
  (or a lone "- None" if the record carried none; one line per live entry)

## Limitations

- <known limitation or deferral carried into release>
  (or a lone "- None")

## Skipped Stages

- <stage> — <why it was a deliberate bypass>
  (or a lone "- None")
```

Relay judgments plainly. If a live Open Questions entry genuinely cannot be
resolved or deferred, say so — do not invent a disposition to force a clean body.
```
