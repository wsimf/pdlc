---
name: pdlc-verify
description: "Use when a PDLC work item has Verification due: audit the implemented and tested work against current source, run journey, UX, and cumulative review, resolve findings with the driver, and post the verification report."
argument-hint: "Parent work item number to verify"
---

# Verify a PDLC Work Item

Prove the Work Item is done rather than assuming it, and record what was verified. You audit claims against current source, `user-journey-reviewer` checks journeys and UX, a general-purpose sub-agent runs the cumulative review, and `pdlc post verify` records the outcome. This skill never edits production source or tests; every fix bounces to its owning stage.

Read `pdlc guide contract` when resolving lifecycle questions. Use [`references/ui-journey-review-prompt.template.md`](references/ui-journey-review-prompt.template.md) and [`references/cumulative-review-prompt.template.md`](references/cumulative-review-prompt.template.md) as dispatch templates.

## Resolve

Require the exact parent work-item number from the conversation. If it is missing or ambiguous, stop and ask; never infer it from a title, branch, file, PR, or history.

Run:

```bash
pdlc inspect verify WORK_ITEM
```

`## Readiness` resolves `Status`, `Gate State`, and whether this pass may run. Not ready → stop, report the reason verbatim, and do nothing further. Keep this output at hand; nothing below needs re-fetching.

At `Changes Required`, also run `pdlc inspect changes WORK_ITEM`. When it lists a CI failure, follow [`references/fix-ci.md`](references/fix-ci.md) in place of Open Comments through Post; it ends at Post, then Report.

`## Source` names the commit this pass verifies. When it lists task PRs that HEAD does not include, check out the top of the task stack, restacked, and re-run `pdlc inspect verify` before auditing; keep the working tree clean until Post.

`## Report` names the report file for this pass. Rows it carries forward are already settled; every row left `null` is checked by the step below that owns it.

This step is complete when `## Readiness` reads ready, `## Source` lists no missing PR, and any change requests are in hand.

## Open Comments

`## Open Comments` lists the still-unresolved review threads on the registered PR stack. **None** → continue to Tasks.

Judge each listed comment by the **Fix** / **Decision** split in Findings: does it call for a source, test, or task-Result change, or does it turn on a product, architecture, UX, safety, or scope call you cannot make? A comment that is a question already answered, addressed by unrelated work already on record, or genuinely not actionable needs neither — note it and continue; don't stop the pass over nothing.

Record each judgment on the comment's `openComments` entry in the report: `finding` when it raised one, citing the comment URL as the finding's source, or `no_action` with why.

- Any comment needing a **Fix** — raise it as an open finding and bounce, as in Findings.
- No Fix, but at least one needing a **Decision** — raise it as a decision finding, as in Findings.
- Leave the rows this pass did not reach `not_run` rather than inventing content.

Either post, made through Post, ends the pass: skip to Report. This step is complete when every listed comment is judged, and any Fix or Decision has been posted.

## Tasks

`## Task Completion` lists which tasks are open and which closed tasks are missing a `## Implementation` comment. For every open task it flags, judge whether its Open Questions deferral is genuine and durable, or the task is on-record as descoped — never invent a reason.

- One or two edge-case tasks incomplete **with** a recorded reason — note and continue.
- Any meaningful work incomplete **without** one, or a leftover-Plan flag — stop, list what's unfinished, and ask the driver.

Linked PRs that are not yet merged or green are not a blocker here; use them only to pick the Cumulative review diff base. Call `pdlc inspect WORK_ITEM` only if you need the body or task bodies beyond `## Task Completion`.

This step is complete when every flagged task has a recorded reason or has stopped the pass.

## Claims

For each claims row the report leaves `null`, read the files its Result names, confirm the behaviour genuinely exists, and spot-check that its acceptance criteria still hold — not merely held when written. Ticked boxes and Result prose are never evidence on their own.

Audit `C-*` constraints scoped to the tasks that bind them — nothing tests a constraint, so confirm each directly in source.

Any discrepancy is a blocking finding for the driver to resolve, never silently patched. This step is complete when every `null` claims row has a result, with a note saying what was checked.

## Journeys and UX

`## Journeys to review` already resolved this: **not applicable** → record both as not applicable and skip this step. Otherwise it lists exactly the journeys to review, in full, plus whether UX needs a fresh pass. Everything carried forward → skip the dispatch; don't re-derive that judgment.

Otherwise dispatch **exactly one** `user-journey-reviewer` call for the whole pass — never per-journey, never a separate UX call. Build the prompt from [`references/ui-journey-review-prompt.template.md`](references/ui-journey-review-prompt.template.md), pasting each journey block straight in; the reviewer knows nothing about PDLC or work item numbers. A journey not found in the current UI section needs your own judgment before dispatch.

A failed journey, design nonconformance, orphaned mapping, unexplained blocked requirement, or material UX finding is a blocking finding. Preserve genuine coverage boundaries rather than treating them as failures. This step is complete when journeys and UX are not applicable, carried forward, or reviewed in one dispatch.

## Cumulative review

Run the project's `cumulative-review` capability over the whole change scope in **one** general-purpose sub-agent dispatch. When the report already carries the cumulative review forward, skip the dispatch.

Build the prompt from [`references/cumulative-review-prompt.template.md`](references/cumulative-review-prompt.template.md); fill its first line from `pdlc inspect capability cumulative-review`. Resolve scope yourself — branch diff against base when unmerged, an explicit commit range when landed in pieces. Never let it fall back to an automatic scope that reviews nothing; ask the driver if you can't establish the base ref. Translate constraints into plain requirements — `FR-*`/`C-*` mean nothing to the sub-agent.

**Any finding of any severity stops the pass.** Report it exactly as prioritised, unaltered. Never write clean evidence while a finding is open. This step is complete when the review is clean, carried forward, or its findings are in hand for Findings.

## Findings

Work through every finding from Claims, Journeys and UX, and Cumulative review with the driver rather than fixing it silently. Do not raise a finding `pdlc inspect verify` already lists as closed. A finding it lists as open is re-checked: mark it `fixed` once the rework holds against current source, or leave it open. Verification is source-read-only: it never edits or commits production or test code.

- **Fix** — status `open`, and set the report's `bounce` to the earliest stage that must rework: `Implementation` for a production change, `Testing` for a coverage or test-only change.
- **Accept** — status `deferred`, with the driver's reason as its note.
- **Decision** — status `decision`, for a finding that turns on a product, architecture, UX, safety, or scope call you cannot make, and that the driver may want to split into its own work item rather than settle inline. Do not use this for a finding you and the driver can just accept — that is **Accept**.

A row whose result is `failed` or `findings` needs a finding about it.

When the audit resumes after a bounce, the report already carries forward every row the rework did not touch; re-verify the rest, originating check first. This step is complete when every finding is marked Fix, Accept, or Decision.

## Post

Fill in the report file `## Report` named — every `null` result, every open comment's action, every listed finding's status, and any new findings — then post it. Run `pdlc post verify --help` for the fields and for how the recommendation, and so the gate, follows from them.

```bash
pdlc post verify WORK_ITEM REPORT_FILE
```

Pass any local files verification produced, or the driver supplied, with `--attachment PATH`; see `pdlc guide attachments`. Do not edit `Product`, `UI`, `Decisions`, or Open Questions yourself. On failure, report the exact error. Read the `gateState` the command returns: `Approval Required` awaits the driver's approval; `Changes Required` with a CI failure goes to [`references/fix-ci.md`](references/fix-ci.md); `CI Pending` means checks are still running and the loop will reconcile it. Never set `Approved` or `Complete`.

This step is complete when the command succeeds and its JSON shows the resulting `gateState`, plus `bouncedTo` for a bounce.

## Report

Relay the command's JSON output, plus:

- the readiness check, and whether Open Comments found and acted on any review comment;
- which rows were carried forward and which were re-checked;
- the claims audit outcome and every specialist outcome;
- how each finding was resolved, by `F-<n>` id: fixed, accepted, or routed to the driver as a decision;
- the gate the command set, and whether `pdlc-complete` can now run — or, for `Decision Required`, that the record is parked for the driver at the `PDLC-DECISION` comment.

If the workflow stopped early, report only the exact blocking condition. The report is complete when it contains the command output, every finding's resolution, the final gate, and the requested human action.

## Boundaries

- Do not edit, commit, or push production source or tests; every fix bounces to its owning stage.
- Do not edit the parent's requirements, UI, Decisions, or Open Questions yourself — evidence, deferrals, and decision blocks go through `pdlc post verify` only.
- Do not edit task scope, criteria, or Results; a wrong Result is a finding, not something to correct here.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, `pdlc post decision`, or `pdlc post complete`; those are driver actions.
- Preserve unrelated staged, unstaged, and untracked work.
- Do not claim delegated review, build, or runtime validation that did not happen, and never settle a row whose check did not run against this pass's HEAD.
