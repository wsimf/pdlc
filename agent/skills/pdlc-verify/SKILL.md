---
name: pdlc-verify
description: "Use when asked to verify a PDLC work item when it has been implemented and tested. This is the last step before completing it."
argument-hint: "Parent work item number to verify"
---

# Verify a PDLC Work Item

Prove the Work Item is done rather than assuming it: audit claims against real source, delegate runtime, UX, and cumulative review to specialists, resolve findings with the driver, and record what was verified — and against which commit — so a later session never has to guess whether the evidence still holds.

This skill may touch production source or tests when resolving an approved finding. `pdlc-complete`, which runs after this reports clean, does not.

Read `pdlc guide contract` before starting.

When verification produces local files, or the driver supplied local files
in this prompt, pass each one to `pdlc post verify` as
`--attachment PATH [--attachment-description TEXT]`. Repeat
`--attachment PATH` for multiple files; a description applies only to the
immediately preceding file. See `pdlc guide attachments`.

## Required input

Require an exact parent work item number. Check the current conversation for an unambiguous one before asking; never infer it from the branch, recent files, open PRs, or history alone.

---

## Step 1: Resolve and confirm readiness

```bash
pdlc inspect verify WORK_ITEM
```

Its `## Readiness` line already resolves `Status`/`Gate State` and the outcome. Not ready → stop, report the reason verbatim, do nothing further. Verification records its own outcome; it never uses `Review Required`. Keep this output at hand — nothing below needs re-fetching.

## Step 2: Check for pending PR review comments early

Step 1's output already carries `## Open Comments` — live, still-unresolved review-thread state off the registered PR stack, not evidence PDLC itself recorded. **None** → continue to Step 3.

Judge each listed comment by the same **Fix** / **Decision** framework Step 7 uses: does it call for a source, test, or task-Result change, or does it turn on a product, architecture, UX, safety, or scope call you cannot make? A comment that is a question already answered, addressed by unrelated work already on record, or genuinely not actionable needs neither — note it and continue to Step 3; don't stop the pass over nothing.

- Any comment needing a **Fix** — post at `Changes Required` with `--bounce STAGE` (Step 8's mechanics), naming `Implementation` for a production change or `Testing` for a coverage/test-only one. Give each acted-on comment its own Findings line, citing the comment's URL from Step 1's output.
- No Fix, but at least one needing a **Decision** — write a `## Decision Required` block per Step 7's shape (question, options, your recommendation, what it blocks, why it is not mechanical) and post at `Decision Required` with `--decision`.
- The report fragment can be short: Claims Audit, User Journeys, UX, and Cumulative Review haven't run yet at this point, so say so plainly rather than inventing content — only an `Approval Required` run is schema-checked.

Either post stops the pass here — skip Steps 3-8 and go straight to Step 9 to report what happened; a resumed pass re-reads `## Open Comments` at Step 1 before repeating this step.

## Step 3: Judge what the mechanical checks can't

`## Task Completion` already resolved which tasks are open and which closed tasks are missing a `## Implementation` comment. For every open task it flags, judge whether its Open Questions deferral is genuine and durable, or the task is on-record as descoped — never invent a reason.

- One or two edge-case tasks incomplete **with** a recorded reason — note and continue.
- Any meaningful work incomplete **without** one, or a leftover-Plan flag — stop, list what's unfinished, ask the driver.

Unmerged or CI-pending PRs are **not** a blocker here: the stack is audited before it lands, and a clean pass is what unblocks the merge. Completion, not Verification, requires every linked PR merged and green. Use the listed PR state only to pick the Step 6 diff base.

Call `pdlc inspect WORK_ITEM` only if you need the body or task bodies beyond `## Task Completion`.

`## Still valid` items need no further work; `## Stale — re-verify` items must be re-verified by the check below that owns that claim kind — this is what keeps a resumed pass cheap.

## Step 4: Audit claims against real source

For each task whose claims row is missing or stale, read the files its Result names, confirm the behaviour genuinely exists, and spot-check acceptance criteria still hold — not merely held when written. Ticked boxes and Result prose are never evidence on their own.

Audit `C-*` constraints scoped to the tasks that bind them — nothing tests a constraint, so confirm each directly in source.

Any discrepancy is a blocking finding for the driver to resolve, never silently patched.

## Step 5: Journeys and UX, in one pass

`## Journeys to review` already resolved this: **not applicable** → record both as not applicable, skip this step. Otherwise it lists exactly the new/stale journeys, full text, plus whether UX needs a fresh pass. Everything already valid → skip the dispatch; don't re-derive that judgment.

Otherwise dispatch **exactly one** `user-journey-reviewer` call for the whole pass — never per-journey, never a separate UX call. Build the prompt from [ui-journey-review-prompt.template.md](references/ui-journey-review-prompt.template.md); paste each journey block straight in — the reviewer knows nothing about PDLC or work item numbers. A journey not found in the current UI section needs your own judgment before dispatch.

A failed journey, design nonconformance, orphaned mapping, unexplained blocked requirement, or material UX finding is a blocking finding. Preserve genuine coverage boundaries rather than treating them as failures.

## Step 6: Cumulative review

Run the project's `cumulative-review` capability over the whole change scope in **one** general-purpose sub-agent dispatch. If every commit since the last `Verified @` touched only work-item paperwork, carry the prior clean result forward without dispatching.

Build the prompt from [cumulative-review-prompt.template.md](references/cumulative-review-prompt.template.md); its first line is filled from `pdlc inspect capability cumulative-review` (the configured skill, or an instruction to review inline). Resolve scope yourself — branch diff against base when unmerged, an explicit commit range when landed in pieces. Never let it fall back to an automatic scope that reviews nothing; ask the driver if you can't establish the base ref. Translate constraints into plain requirements — `FR-*`/`C-*` mean nothing to the sub-agent.

**Any finding of any severity stops the pass.** Report exactly as prioritised, unaltered. Never write clean evidence while a finding is open.

## Step 7: Resolve findings with the driver

Work through every finding from Steps 4-6 with the driver rather than fixing silently. **Verification is source-read-only** — it never commits production or test code, because a fix made here has no push, linked PR, CI, merge, or owning-stage reapproval behind it:

- **Fix** — bounce to the owning stage: post at `Changes Required` with `--bounce STAGE` (Step 8), `Implementation` for a production change, `Testing` for a coverage or test change. The script returns that stage to `Stale` with no driver step, and the record goes back through review, approval, and testing before this audit resumes. Never edit source from this skill.
- **Accept** — note the finding and the driver's reason; it becomes a one-line Open Questions deferral when the report posts (Step 8 writes it, not you).
- **Decision** — for a finding that turns on a product, architecture, UX, safety, or scope call you cannot make, and that the driver may want to split into its own work item rather than settle inline. Write it as a `## Decision Required` block (question, options, your recommendation, what it blocks, why it is not mechanical) and post at `Decision Required` (Step 8). The autonomous loop halts; the driver clears it with `pdlc guide decisions` (`pdlc post decision`), which returns the record to `Changes Required` for a re-verify with any deferred point out of scope. Do not use this for a finding you and the driver can just accept — that is **Accept**.

Every finding that turns on a production-source, test, or task-Result change goes back to its owning stage via `--bounce STAGE` (Step 8), naming the earliest stage that must rework — `Implementation`, or `Testing` for a coverage or test-only gap. The script returns that stage to `Stale` itself (no driver step) and the record goes back through review, approval, and testing before this audit resumes; the bounce is what advances the churn loop count. When the audit resumes after a bounce, don't blanket re-run everything — diff the reworked commits against each item's scope files and re-verify only what they actually touched, originating check first.

## Step 8: Post the verification report

`pdlc post verify` assembles the comment, writes the Findings section, files deferrals into Open Questions, and sets the gate from `--recommendation`. Give it these inputs; make no formatting decisions yourself.

1. A report fragment with only Claims Audit, User Journeys, UX, and Cumulative Review sections. Every item carries the `Verified @` commit the check actually ran against — never "now":

   ```md
   ### Claims Audit
   - WORK-142-TASK-007 — Confirmed: `RouteShapeAnimator` matches Result; C-2 holds (Verified @ a1b2c3d)
   ### User Journeys
   - UJ-3 — Accepted: offline retry confirmed in the running app (Verified @ a1b2c3d)
   ### UX
   - Reviewed — no critical findings (Verified @ a1b2c3d)
   ### Cumulative Review
   - Clean — no findings (Verified @ a1b2c3d)
   ```

   One line per task with a Result under Claims Audit, never blank. A journey is `Accepted` or `Deferred` with a matching Open Questions entry. `Not applicable` for User Journeys/UX with no UI. Cumulative Review reads `Clean` only once every finding is genuinely resolved.

2. A fixed-findings file, one `description | commit` per line, only for findings a prior bounce's rework resolved and this pass has since re-verified against the named commit. Omit or leave empty if nothing was re-verified this pass.

3. A deferred-findings file, one line per driver-accepted finding. Omit or leave empty if nothing deferred.

4. `--decision` with a file of `## Decision Required` blocks — only when `--recommendation "Decision Required"`, and required then.

5. `--bounce STAGE` — only with `--recommendation "Changes Required"`, when a finding needs an upstream stage to rework (Step 7). Records the target and named loop in `PDLC-REVIEW` and returns that stage to `Stale`, no driver step.

```bash
pdlc post verify WORK_ITEM /tmp/pdlc-report.md \
    --recommendation "Approval Required" \
    --fixed /tmp/pdlc-fixed.txt \
    --deferred /tmp/pdlc-deferred.txt
```

`--recommendation` is `Approval Required` once every finding is fixed or accepted, `Decision Required` (with `--decision`) when a finding was routed to the driver in Step 2 or Step 7, and `Changes Required` when you are stopping mid-pass — with `--bounce STAGE` when the rework belongs to an upstream stage, without it when you can reconcile it in a re-verify. The script sets the gate: `Approval Required` awaits the driver's approval then `pdlc-complete`; plain `Changes Required` and (after `pdlc post decision`) `Decision Required` route back to `pdlc-verify`; `--bounce` routes to the named stage's owner. Do not edit `Product`, `UI`, `Decisions`, or Open Questions yourself — this script is the only thing that writes to the body at this stage.

**There is no `pdlc-verify.sh`**, and the stage publishers (`pdlc post implement`, `pdlc post test`) land `Review Required`, which Verification doesn't use — don't reach for them. Stop after posting (report the blocker if the workflow stopped early). Never set `Approved` or `Complete` from this skill.

## Step 9: Report

Report the readiness check, whether Step 2 found and acted on any open PR review comments, what reuse found still valid vs. stale, the claims audit outcome, every specialist outcome, how each finding was resolved (fixed / accepted / routed to the driver as a decision), the final report content, and the gate the script set. If the workflow stopped early, report only the exact blocking condition. Say plainly whether `pdlc-complete` can now run, or — for `Decision Required` — that the record is parked for the driver at the `PDLC-DECISION` comment.

---

## Boundaries

- Do not edit the parent's requirements, UI, Decisions, or Open Questions yourself — evidence, deferrals, and decision blocks go through `pdlc post verify`'s `--fixed`/`--deferred`/`--decision` only.
- Do not edit task scope, criteria, or Results; a wrong Result is a finding, not something to correct here.
- Do not set `Status = Complete` — that's `pdlc-complete`, on explicit driver instruction.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, `pdlc post decision`, or `pdlc post complete` — driver-only.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim delegated review, build, or runtime validation that did not happen, and never mark an item `Verified @` a commit the check wasn't run against.

## Checklist

- [ ] `Status` is `Verification`, gate was `Pending`, `Changes Required`, or `Stale`
- [ ] `## Open Comments` checked before anything else; a Fix- or Decision-worthy one posted and stopped the pass
- [ ] Every task closed or explicitly deferred on record (PR merge and CI state are completion's bar, not checked here)
- [ ] Prior evidence reused only where `git log` proved its scope untouched
- [ ] `pdlc inspect verify` checked so no already-fixed/deferred finding was raised again
- [ ] Every stale claim checked against current source, constraints included
- [ ] Journeys/UX ran in one `user-journey-reviewer` dispatch, or recorded not applicable
- [ ] Cumulative review ran in one dispatch over a scope you resolved, and is clean, or the workflow stopped
- [ ] Every finding fixed and re-verified, accepted with a reason for `--deferred`, or routed to the driver as a `## Decision Required` block via `--decision`
- [ ] Every item carries the real commit its check ran against
- [ ] Report posted via `pdlc post verify` with an explicit `--recommendation`, plus `--fixed`/`--deferred`/`--decision` as they apply
