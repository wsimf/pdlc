---
name: pdlc-verify
description: "Use when a PDLC work item has Verification due: audit the implemented and tested work against current source, run journey, UX, and cumulative review, resolve findings with the driver, and post the verification report."
argument-hint: "Parent work item number to verify"
---

# Verify a PDLC Work Item

Prove the Work Item is done rather than assuming it, and record what was verified against which commit. You audit claims against current source, `user-journey-reviewer` checks journeys and UX, a general-purpose sub-agent runs the cumulative review, and `pdlc post verify` records the outcome. This skill never edits production source or tests; every fix bounces to its owning stage.

Read `pdlc guide contract` when resolving lifecycle questions. Use [`references/ui-journey-review-prompt.template.md`](references/ui-journey-review-prompt.template.md) and [`references/cumulative-review-prompt.template.md`](references/cumulative-review-prompt.template.md) as dispatch templates.

## Resolve

Require the exact parent work-item number from the conversation. If it is missing or ambiguous, stop and ask; never infer it from a title, branch, file, PR, or history.

Run:

```bash
pdlc inspect verify WORK_ITEM
```

`## Readiness` resolves `Status`, `Gate State`, and whether this pass may run. Not ready → stop, report the reason verbatim, and do nothing further. Keep this output at hand; nothing below needs re-fetching.

At `Changes Required`, also run `pdlc inspect changes WORK_ITEM`. When it lists a CI failure, follow [`references/fix-ci.md`](references/fix-ci.md) in place of Open Comments through Post; it ends at Post, then Report.

This step is complete when `## Readiness` reads ready and any change requests are in hand.

## Open Comments

`## Open Comments` lists the still-unresolved review threads on the registered PR stack. **None** → continue to Tasks.

Judge each listed comment by the **Fix** / **Decision** split in Findings: does it call for a source, test, or task-Result change, or does it turn on a product, architecture, UX, safety, or scope call you cannot make? A comment that is a question already answered, addressed by unrelated work already on record, or genuinely not actionable needs neither — note it and continue; don't stop the pass over nothing.

- Any comment needing a **Fix** — post at `Changes Required` with `--bounce STAGE`, naming `Implementation` for a production change or `Testing` for a coverage/test-only one. Give each acted-on comment its own finding line, citing the comment's URL.
- No Fix, but at least one needing a **Decision** — write a `## Decision Required` block in the Findings shape and post at `Decision Required` with `--decision`.
- The report fragment can be short: say plainly that Claims Audit, User Journeys, UX, and Cumulative Review have not run yet, rather than inventing content.

Either post, made through Post, ends the pass: skip to Report. This step is complete when every listed comment is judged, and any Fix or Decision has been posted.

## Tasks

`## Task Completion` lists which tasks are open and which closed tasks are missing a `## Implementation` comment. For every open task it flags, judge whether its Open Questions deferral is genuine and durable, or the task is on-record as descoped — never invent a reason.

- One or two edge-case tasks incomplete **with** a recorded reason — note and continue.
- Any meaningful work incomplete **without** one, or a leftover-Plan flag — stop, list what's unfinished, and ask the driver.

Linked PRs that are not yet merged or green are not a blocker here; use them only to pick the Cumulative review diff base. Call `pdlc inspect WORK_ITEM` only if you need the body or task bodies beyond `## Task Completion`.

`## Still valid` items need no further work; `## Stale — re-verify` items must be re-verified by the step below that owns that claim kind. This step is complete when every flagged task has a recorded reason or has stopped the pass.

## Claims

For each task whose claims row is missing or stale, read the files its Result names, confirm the behaviour genuinely exists, and spot-check that its acceptance criteria still hold — not merely held when written. Ticked boxes and Result prose are never evidence on their own.

Audit `C-*` constraints scoped to the tasks that bind them — nothing tests a constraint, so confirm each directly in source.

Any discrepancy is a blocking finding for the driver to resolve, never silently patched. This step is complete when every missing or stale claim has been checked against current source and its commit noted.

## Journeys and UX

`## Journeys to review` already resolved this: **not applicable** → record both as not applicable and skip this step. Otherwise it lists exactly the new or stale journeys, in full, plus whether UX needs a fresh pass. Everything already valid → skip the dispatch; don't re-derive that judgment.

Otherwise dispatch **exactly one** `user-journey-reviewer` call for the whole pass — never per-journey, never a separate UX call. Build the prompt from [`references/ui-journey-review-prompt.template.md`](references/ui-journey-review-prompt.template.md), pasting each journey block straight in; the reviewer knows nothing about PDLC or work item numbers. A journey not found in the current UI section needs your own judgment before dispatch.

A failed journey, design nonconformance, orphaned mapping, unexplained blocked requirement, or material UX finding is a blocking finding. Preserve genuine coverage boundaries rather than treating them as failures. This step is complete when journeys and UX are recorded not applicable, still valid, or reviewed in one dispatch.

## Cumulative review

Run the project's `cumulative-review` capability over the whole change scope in **one** general-purpose sub-agent dispatch. If every commit since the last `Verified @` touched only work-item paperwork, carry the prior clean result forward without dispatching.

Build the prompt from [`references/cumulative-review-prompt.template.md`](references/cumulative-review-prompt.template.md); fill its first line from `pdlc inspect capability cumulative-review`. Resolve scope yourself — branch diff against base when unmerged, an explicit commit range when landed in pieces. Never let it fall back to an automatic scope that reviews nothing; ask the driver if you can't establish the base ref. Translate constraints into plain requirements — `FR-*`/`C-*` mean nothing to the sub-agent.

**Any finding of any severity stops the pass.** Report it exactly as prioritised, unaltered. Never write clean evidence while a finding is open. This step is complete when the review is clean, carried forward, or its findings are in hand for Findings.

## Findings

Work through every finding from Claims, Journeys and UX, and Cumulative review with the driver rather than fixing it silently. Do not raise a finding `pdlc inspect verify` already lists as fixed or deferred. Verification is source-read-only: it never edits or commits production or test code.

- **Fix** — bounce to the owning stage: post at `Changes Required` with `--bounce STAGE`, naming the earliest stage that must rework — `Implementation` for a production change, `Testing` for a coverage or test-only change.
- **Accept** — note the finding and the driver's reason, and pass it through `--deferred`.
- **Decision** — for a finding that turns on a product, architecture, UX, safety, or scope call you cannot make, and that the driver may want to split into its own work item rather than settle inline. Write it as a `## Decision Required` block (question, options, your recommendation, what it blocks, why it is not mechanical) and post at `Decision Required`. Do not use this for a finding you and the driver can just accept — that is **Accept**.

When the audit resumes after a bounce, don't blanket re-run everything — diff the reworked commits against each item's scope files and re-verify only what they actually touched, originating check first. This step is complete when every finding is marked Fix, Accept, or Decision.

## Post

Prepare the inputs `pdlc post verify` takes; run `pdlc post verify --help` for their formats and for what each recommendation does to the gate.

- **Report fragment** — the Claims Audit, User Journeys, UX, and Cumulative Review sections only. Every item carries the `Verified @` commit its check actually ran against — never "now". One line per task with a Result under Claims Audit, never blank. A journey is `Accepted`, or `Deferred` with a matching Open Questions entry. `Not applicable` for User Journeys and UX with no UI. Cumulative Review reads `Clean` only once every finding is genuinely resolved.
- **`--fixed`** — only findings a prior bounce's rework resolved and this pass has since re-verified against the named commit.
- **`--deferred`** — only findings the driver accepted in Findings.
- **`--decision`** — the `## Decision Required` blocks, with `--recommendation "Decision Required"`.
- **`--bounce STAGE`** — the stage Findings named for rework, with `--recommendation "Changes Required"`.

Recommend `Approval Required` once every finding is fixed or accepted, `Decision Required` when a finding went to the driver in Open Comments or Findings, and `Changes Required` when you are stopping mid-pass — with `--bounce STAGE` when the rework belongs upstream, without it when you can reconcile it in a re-verify.

```bash
pdlc post verify WORK_ITEM /tmp/pdlc-report.md \
    --recommendation "Approval Required" \
    --fixed /tmp/pdlc-fixed.txt \
    --deferred /tmp/pdlc-deferred.txt
```

Pass any local files verification produced, or the driver supplied, with `--attachment PATH`; see `pdlc guide attachments`. Do not edit `Product`, `UI`, `Decisions`, or Open Questions yourself. On failure, report the exact error. Read the `gateState` the command returns: `Approval Required` awaits the driver's approval; `Changes Required` with a CI failure goes to [`references/fix-ci.md`](references/fix-ci.md); `CI Pending` means checks are still running and the loop will reconcile it. Never set `Approved` or `Complete`.

This step is complete when the command succeeds and its JSON shows the resulting `gateState`, plus `bouncedTo` for a bounce.

## Report

Relay the command's JSON output, plus:

- the readiness check, and whether Open Comments found and acted on any review comment;
- what was still valid and what was stale;
- the claims audit outcome and every specialist outcome;
- how each finding was resolved: fixed, accepted, or routed to the driver as a decision;
- the gate the command set, and whether `pdlc-complete` can now run — or, for `Decision Required`, that the record is parked for the driver at the `PDLC-DECISION` comment.

If the workflow stopped early, report only the exact blocking condition. The report is complete when it contains the command output, every finding's resolution, the final gate, and the requested human action.

## Boundaries

- Do not edit, commit, or push production source or tests; every fix bounces to its owning stage.
- Do not edit the parent's requirements, UI, Decisions, or Open Questions yourself — evidence, deferrals, and decision blocks go through `pdlc post verify` only.
- Do not edit task scope, criteria, or Results; a wrong Result is a finding, not something to correct here.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, `pdlc post decision`, or `pdlc post complete`; those are driver actions.
- Preserve unrelated staged, unstaged, and untracked work.
- Do not claim delegated review, build, or runtime validation that did not happen, and never mark an item `Verified @` a commit the check wasn't run against.
