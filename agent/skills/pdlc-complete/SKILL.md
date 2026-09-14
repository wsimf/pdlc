---
name: pdlc-complete
description: "Close out a verified PDLC record: confirm verification is clean, capture what shipped as structured completion evidence, and lock the record at Complete on an explicit driver instruction. Use when the driver says a record is done or asks to complete or finalise it."
argument-hint: "Parent work item number to complete"
---

# Complete a PDLC record

Close out one PDLC record: confirm `pdlc-verify` has already proven it is done, capture what shipped as completion evidence, and lock it. This skill is record-only — it never touches source or tests, and never re-runs verification; that all lives in `pdlc-verify`, which must run first.

Completion does not edit the verified record. Product, UI, requirement, and task wording are frozen at Verification — any substantive change to them is a new parent work item, or a bounce to the owning stage and re-verification. The only parent-body edit `pdlc post complete` makes is blanking the now-settled `## Open Questions` section to a pointer; every decision that emerged during delivery and every open-question resolution is recorded in the completion evidence comment instead.

Pass any local files the completion evidence includes — including any the driver supplied in this prompt — to `pdlc post complete` with `--attachment PATH`; see `pdlc guide attachments`.

Read `pdlc guide contract` before checking readiness.

## Required input

Require an exact parent work item number. Check the current conversation for an unambiguous one before asking; never infer it from the branch, recent files, open PRs, or history alone.

Completion also requires an **explicit driver instruction to complete this record, in this turn**, naming it. Never complete on a verifier's recommendation, because the state looks finished, because approval was implied earlier, or as a step folded into some other action.

---

## Step 1: Confirm the record is actually ready

```bash
pdlc inspect complete WORK_ITEM
```

`## Readiness` applies the same checks `pdlc post complete` enforces. Any `Not ready` line means stop, report it verbatim, do nothing further. When it reports `Ready`, `## Task Completion`, `## Verification Evidence`, and `## Open Questions` still print the detail — read every listed item's actual wording yourself: every claims row must read `Confirmed`, every journey `Accepted` or `Deferred`, UX `reviewed` or `Not applicable`, cumulative review `clean`. A line that passes the check but doesn't actually say that is still not ready — judging what the words say is yours, not the command's. `## Open Questions` lists the live entries your completion evidence must disposition.

For any open task or stale item, look for an explicit on-record reason — the same comments, or an explicit descope note on the task. Never invent one.

- One or two edge cases incomplete **with** a recorded reason — note them and continue.
- Any meaningful work incomplete **without** one, any stale Verification item, even a single task — stop. List exactly what's unfinished, and ask the driver whether to finish it, descope it explicitly, or explain what's missing. A stale item sends the driver back to `pdlc-verify`.

Read the whole record before continuing: the parent body end to end, every task body and Result, and the evidence comments in order.

## Step 2: Dispatch `pdlc-completer`

Spawn once, building the prompt from [`references/completer-prompt.md`](references/completer-prompt.md) — the full parent body, every task body and `## Implementation` comment, the verification evidence, the linked PRs and their state, the decisions and open questions as they stand, and any skipped stage.

It prepares the completion evidence body: what shipped, the verification reference, the decisions that emerged during delivery, a Resolved/Deferred disposition for every live Open Questions entry, release limitations, and any skipped stage. It does not mutate the work item, does not edit the record, and does not complete anything.

Wait for its report. Relay its judgments without reinterpreting them. If the completer says a question genuinely cannot be resolved or deferred, stop — the record is not ready.

## Step 3: Lock the record

Run it only on the driver's explicit instruction from this turn. Write the completion evidence body to a file and pass its path:

```bash
pdlc post complete WORK_ITEM /tmp/pdlc-complete-evidence.md
```

The body has all six `##` sections:

```markdown
## Shipped

Offline tile pinning across 7 tasks, PRs #144-#153, all merged.

## Verification

clean @ a1b2c3d — claims, 4 journeys, UX reviewed, cumulative review clean.

## Decisions

- Evict pinned tiles LRU once the regional cap is hit — simpler than a manual queue (WORK-142-TASK-004).

## Open Questions

- Should tile eviction be LRU or manual-only? — Resolved: LRU, capped per region.
- Do we cap pinned regions at five? — Deferred: revisit for the paid tier, tracked as #210.

## Limitations

- Pre-existing profile migration deferred to a follow-up record.

## Skipped Stages

- None
```

All six `##` sections are required. **Decisions**, **Limitations**, and **Skipped Stages** are a bulleted list or a lone `- None`. **Open Questions** carries one line per live entry from the record — `<question> — Resolved: <answer>` or `<question> — Deferred: <what>, tracked as <ref>` — or a lone `- None` when the record had none; the parser rejects a body that leaves any live entry unaccounted for. **Verification** must state `clean @ <commit>`.

A successful call leaves the record at `Complete`. A completion claim in prose is not a completion transition. If the script fails, report the exact failure; do not describe the record as complete.

## Step 4: Report

Report the Step 1 readiness check and the verification state it relied on, the decisions and open-question dispositions recorded in the evidence, any limitation or deferral carried forward, and the completion transition. If the workflow stopped early, report the exact blocking condition and nothing further.

Completed records are locked. Only a mechanical, non-semantic fix — a typo, a broken link — may be made in place afterwards, recorded with a transition evidence comment. Anything substantive needs a new parent work item.

---

## Boundaries

- Do not edit source, tests, project files, other documentation, agents, or skills.
- Do not build, test, render, run the app, or push.
- Do not re-run verification, journeys, UX review, or cumulative review — `pdlc-verify` owns all of it.
- Do not edit the verified record — Product, UI, requirement, and task wording are frozen. A substantive change bounces to its owning stage and re-verification, or becomes a new parent work item. `pdlc post complete`'s Open Questions blanking is the only permitted parent-body edit.
- Do not run `pdlc post approve`, `pdlc post skip`, or `pdlc post invalidate` — driver-only, like completion itself.
- Do not write lifecycle state into the work item body — those fields are script-owned.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim delegated evidence preparation, review, or runtime validation that did not happen.

## Checklist

- [ ] The driver explicitly asked to complete this exact record, in this turn
- [ ] `## Readiness` from `pdlc inspect complete` reports ready
- [ ] Every delivery task closed; every linked PR merged or dispositioned with checks passing
- [ ] `## Verification Evidence` shows nothing stale, and every line's wording actually says Confirmed/Accepted/Deferred/reviewed/clean, or the driver sent it back to `pdlc-verify`
- [ ] Unfinished work has an explicit recorded reason, or the workflow stopped
- [ ] Completion evidence has all six sections; Decisions capture only what shaped what shipped, no changelog
- [ ] Every live Open Questions entry is dispositioned Resolved or Deferred in the evidence
- [ ] The verified record was not edited beyond the script's Open Questions blanking
- [ ] Locked with `pdlc post complete`, and reported only after it actually succeeded
