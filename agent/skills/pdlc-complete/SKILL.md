---
name: pdlc-complete
description: "Close out a verified PDLC record: confirm verification is clean, capture what shipped as structured completion evidence, and lock the record at Complete on an explicit driver instruction. Use when the driver says a record is done or asks to complete or finalise it."
argument-hint: "Parent work item number to complete"
---

# Complete a PDLC record

Close out one verified PDLC record, and only on the driver's explicit instruction. `pdlc inspect complete` confirms `pdlc-verify` has already proven it is done, `pdlc-completer` prepares the completion evidence, and `pdlc post complete` locks the record. This skill is record-only: it never touches source or tests, and never re-runs verification.

Read `pdlc guide contract` when resolving lifecycle questions. Use [`references/completer-prompt.md`](references/completer-prompt.md) as the dispatch template.

## Resolve

Require the exact parent work-item number from the conversation. If it is missing or ambiguous, stop and ask; never infer it from a title, branch, file, PR, or history.

Completion also requires an **explicit driver instruction to complete this record, in this turn**, naming it. Never complete on a verifier's recommendation, because the state looks finished, because approval was implied earlier, or as a step folded into some other action.

Run:

```bash
pdlc inspect complete WORK_ITEM
```

Any `Not ready` line in `## Readiness` means stop, report it verbatim, and do nothing further. When it reports `Ready`, the verification rows and findings are already machine-checked; read `## Task Completion` and `## Open Questions` yourself. `## Open Questions` lists the live entries your completion evidence must disposition.

This step is complete when the driver's instruction is in hand, `## Readiness` reads `Ready`, and every listed item's wording has been read.

## Judge

For any open task or stale item, look for an explicit on-record reason — the evidence comments, or an explicit descope note on the task. Never invent one.

- One or two edge cases incomplete **with** a recorded reason — note them and continue.
- Any meaningful work incomplete **without** one, or any stale Verification item — stop. List exactly what's unfinished, and ask the driver whether to finish it, descope it explicitly, or explain what's missing. A stale item sends the driver back to `pdlc-verify`.

Then read the whole record: the parent body end to end, every task body and Result, and the evidence comments in order. This step is complete when every open or stale item has a recorded reason and the whole record has been read.

## Dispatch

Spawn `pdlc-completer` once, building the prompt from [`references/completer-prompt.md`](references/completer-prompt.md) — the full parent body, every task body and `## Implementation` comment, the verification evidence, the linked PRs and their state, the decisions and open questions as they stand, every `PDLC-PATCHED` comment, and any skipped stage.

Wait for its report. Relay its judgments without reinterpreting them. If the completer says a question genuinely cannot be resolved or deferred, stop — the record is not ready. This step is complete when the report holds an evidence body with every live Open Questions entry dispositioned.

## Lock

Write the completion evidence body to a local file; `pdlc post complete --help` gives its required sections and format. Pass any local files the evidence includes, or the driver supplied, with `--attachment PATH`; see `pdlc guide attachments`.

```bash
pdlc post complete WORK_ITEM /tmp/pdlc-complete-evidence.md
```

A completion claim in prose is not a completion transition. If the command fails, report the exact failure and do not describe the record as complete. This step is complete when the command's JSON shows `completed: true`.

## Report

Relay the command's JSON output, plus the readiness check and the verification state it relied on, the decisions and open-question dispositions recorded in the evidence, and any limitation or deferral carried forward.

If the workflow stopped early, report only the exact blocking condition. The report is complete when it contains the command output, every open-question disposition, and the completion transition.

## Boundaries

- Do not edit source, tests, project files, other documentation, agents, or skills.
- Do not build, test, render, run the app, or push.
- Do not re-run verification, journeys, UX review, or cumulative review; `pdlc-verify` owns all of it.
- Do not edit the verified record yourself; a substantive change bounces to its owning stage or becomes a new parent work item.
- Use the CLI as the only work-item interface, and never write lifecycle state into the work item body.
- Do not run `pdlc post approve` or `pdlc post skip`; those are driver actions.
- Execute `pdlc post invalidate` when explicitly authorized by the driver; authorization persists across turns within the agreed work-item, stage, and task scope until fulfilled or revoked. Do not initiate invalidation autonomously.
- Preserve unrelated staged, unstaged, and untracked work.
- Do not claim delegated evidence preparation, review, or runtime validation that did not happen.
