---
name: pdlc
description: "Route PDLC intake. Given an exact work item number, read its work item, current state, delivery tasks, PRs, current source, and Git history, then report where it stands and what is due next without changing anything. Given a fresh feature idea with no parent work item, invoke pdlc-write to create the reviewed parent record. Use when asked to start, orient on, resume, or check the status of a PDLC item."
argument-hint: "work item number to orient on, or a fresh feature idea to start"
---

# PDLC orchestrator

The Product Development Life Cycle runs on a PDLC work item and its lifecycle state. This skill does exactly two things: create a new PDLC Work Item from an idea, or orient on an existing one and report.

## Modes

Decide which of two modes applies before doing anything else:

| Input | Mode |
|---|---|
| A concrete fresh feature idea, with no PDLC Work Item yet | **Start** — hand it to `pdlc-write`, report, stop. |
| An exact PDLC Work Item number | **Orient** — read everything, report, stop. |

Never infer an work item number or a feature idea from the branch, recent files, open PRs, or conversation history. If the input is missing, malformed, ambiguous, or names a piece of work which is not a PDLC work item, stop and ask rather than guessing.

---

## Start mode

Invoke `pdlc-write` skill with the idea.
If the driver supplied mockups or other local files with the idea, pass their paths to `pdlc-write` so it can attach them; write any pasted image to a local path first.

Report what `pdlc-write` returns:

```md
Created Work Item #<number> — <title>
Slug: <slug>   Item ID: <itemId>
Status: Product, Gate State: Approval Required, Lifecycle: Planning

Due next: Product.ApprovalRequired → human
Approve to proceed
```
Once done, wait for the driver to approve the Product stage before continuing. Run `pdlc post approve` with the provided Work Item number to approve the Product stage. Then continue with the Orient mode steps below.

## Orient mode

Strictly read-only. Do not edit source, tests, docs, the work item, or work item state, and do not run any mutating `pdlc-*` script. Do not run formatting, code generation, or build-fix commands.

Treat the work item as **current intent only** — a specification, not a log. Treat Git history as the record of how it got there, and treat source as the final source of truth whenever the two disagree. Never infer that a review happened, a gate was approved, or a task was completed from work item prose or ticked checkboxes; only work item state and recorded evidence count.

### Lifecycle context

Before continuing, read `references/pdlc-contract.md` for record identity, lifecycle, human boundaries, evidence semantics, and idempotency.

When diagnosing a stage transition, skip, or malformed state, also read `references/pdlc-workflow.md`. When `# Due Next` routes to `pdlc-post-ci` (`Gate State` is `CI Pending`), read `references/resolve-ci.md` before reporting what to do on continue. When evaluating invalidation, override approval, Verification, or completion guarantees, read `references/parity-contract.md`. Consult `references/stage-ownership.md` only to explain the owner and artifact returned by `# Due Next`, never to replace its routing. Consult `references/commands.md` only when a command's mutation authority is unclear.

1. **Resolve and read the record.** `pdlc inspect <work-item>` — compact work-item metadata including normalized `workType`, classified task tree, linked PR summary, a pointer to the full body in a temp file, and `# Due Next` (pipeline routing already applied). Read the pointed-to file when the full body is needed; use `--full` only when inline content is useful. No comments. No item, ambiguous match, unknown work type, or unavailable pipeline is a hard stop — do not fall back to a title search or another pipeline.
2. **Read the evidence comments.** `pdlc inspect timeline <work-item>` — chronological, marker-stripped, grouped by stage (marker vocabulary: `references/pdlc-contract.md`). Use `pdlc inspect comments <work-item> --page N` to inspect the raw discussion in bounded newest-first pages of 100; it reports the total and next page command. Reconcile against work item state; flag disagreement.
3. **Read the delivery tasks.** Already classified in `pdlc inspect`'s `# Tasks` section. Pull full bodies with `pdlc inspect task DELIVERY_TASK [...]` only where the summary leaves a real question about dependencies, HITL/AFK, or acceptance criteria.
4. **Check linked PRs and checks** from `pdlc inspect`'s `pullRequests` field — it already carries the check rollup; don't re-derive it.
5. **Check the worktree and relevant history.** Always run `git status --short`. From Implementation onward, run `git log --oneline --decorate --all --grep='<work item/task/file terms>'`. For earlier stages, report `Not applicable — pre-implementation` unless current source indicates the feature already exists.
6. **Check for source drift.** Use `rg` and direct reads for concrete types, methods, files, and flags named by the parent work item or evidence timeline; when step 6 inspected Git history, use it to explain when they changed.
7. **Read `# Due Next`** directly — it already applied `Status`/`Gate State` and any skips. Don't re-derive it.

Then report. Fill every section — write `None` explicitly rather than omitting one:

```md
Orientation complete. Worktree is <clean|dirty>.

Work Item: #<number> — <title>
Work Type: <workType>
Slug: <slug>   Item ID: <itemId>
Status: <stage>, Gate State: <state>, Lifecycle: <state>
Skipped States: <list, or None>

We are building <one-sentence product/architecture summary>.

Stage artifacts:
- Product: <present and covering what, or absent>
- UI: <required | not required | absent>
- Tasks: <n total, n closed, n open>
- Technical Plan: <n of n incomplete tasks planned>
- Testing / Verification: <recorded evidence, or none>

Delivery tasks:
- #<n> WORK-NNN-TASK-NNN <title> — <open|closed>, plan <yes|no>, result <yes|no>, PR <link|none>

Evidence on record:
- <marker> — <what it claims> (<date>)

Drift and anomalies:
- <work item or evidence claim> but source, Git history, or PR state shows <truth at path:line or commit>
- <stale gate, invalid transition, artifact changed after approval, task closed with no `## Implementation` comment, evidence disagreeing with work item state>
- `None found` only if checks in steps 3 and 5–7 found no disagreement

Git history:
- <relevant commits and what they explain, or Not applicable — pre-implementation>

Due next: <Status>.<Gate State> → <owning specialist skill, or human>
To proceed, ask for: <the exact next instruction to give>
```

Keep every line grounded in something actually inspected. Do not claim build, test, runtime, UX, or runtime evidence that was not produced in this turn or explicitly recorded on the work item. Stop after the report.

Continue to drive the work item forward after the driver intends to proceed by invoking the appropriate skill specified in references/stage-ownership.md.

If `# Due Next` routes to `human-input`, Product authoring or re-authoring needs an interactive driver. Report that `pdlc-write` is required and stop; invoke it only when the driver explicitly asks to proceed.

## CI pending

If `# Due Next` routes to `pdlc post ci` — `Gate State` is `Implementation / CI Pending`, the stage review passed and the registered PR stack's CI has not settled — orientation just reports it and the live `pullRequests` check state. Do not run `pdlc post ci` during read-only orientation.

Once the driver asks to continue, follow `references/resolve-ci.md`: still-running means wait; green runs `pdlc post ci` to reach `Approval Required`; red runs `pdlc post ci` (posting a `PDLC-IMPLEMENTATION` note, dropping to `Changes Required`) and then `pdlc-implement` picks it up. `pdlc post ci` is mechanical and refuses any gate other than `CI Pending`.

## Blocked decision

If `# Due Next` routes to `human-decision` — `Gate State` is `Decision Required`, a post-publication reviewer or the Verification audit raised a finding only the driver can settle — orientation still just reports it. Do not resolve it during read-only orientation.

Once the driver asks to resolve the decision, read `references/decision-resolver-workflow.md` and follow it end to end: it walks each open `## Decision Required` block, puts it to the driver with the reviewer's recommendation and a defer option, and lands every outcome in one `pdlc post decision <work-item> --manifest FILE` call — each decision either answered or deferred into its own `Product / Pending` work item. That command is driver-only and mutates the record — never run it without an explicit instruction naming this record in this turn.
