# Commands

Only `pdlc post ...` commands mutate the PDLC work item store. Specialists prepare artifacts and evidence; the commands publish them.

`pdlc post` commands also accept repeated local attachment inputs in the form
`--attachment PATH [--attachment-description TEXT]`. They store files under
`.pdlc/<work-item-number>/attachments/` and never publish attachment metadata
to the work item store.

| Script | Purpose | Who may run it |
|---|---|---|
| `pdlc inspect` | Resolve a work item to its state, classified delivery task tree, compact linked-PR summary, full-body temp-file pointer, and routing decision (`Due Next`), read-only even through a skip cascade. Use `--full` for the complete inspection on stdout. | Anyone — read-only. |
| `pdlc inspect task` | Render one or more delivery tasks in full, front matter plus body. | Anyone — read-only. |
| `pdlc inspect timeline` | Render every evidence comment on a work item as a chronological, marker-stripped timeline (compact index by default, `--full` for the whole thing on stdout). | Anyone — read-only. |
| `pdlc inspect verify` | Readiness, task completion, timeline, journeys-to-review, and reuse/staleness report for a Verification pass. | Anyone — read-only. |
| `pdlc inspect complete` | Readiness, task completion, and Verification-evidence staleness report for a completion pass. | Anyone — read-only. |
| `pdlc inspect test` | Readiness and testable-scope (closed tasks with a Result, their PRs' real touched files) report for a Testing pass. | Anyone — read-only. |
| `pdlc inspect implement` | Readiness and the single next eligible delivery task (OPEN, planned, not yet implemented) in CORE-before-UI order, with its Technical Plan and the `gh stack` setup command for its branch inline. | Anyone — read-only. |
| `pdlc inspect review` | Readiness and the Status→artifact→reviewer-agent mapping for a review pass. | Anyone — read-only. |
| `pdlc inspect capability [SLOT]` | Resolve the project's capability routing from `.pdlc/config.toml` (`[agents]`, `[skills]`). No arg dumps every slot; a slot name emits one line to paste into a sub-agent brief — the sub-agent to dispatch to, or the "invoke this skill first" instruction (with an inline fallback when the slot is unset). See `references/capabilities.md`. | Anyone — read-only. |
| `pdlc next` | Report the routing decision for one item, or scan the queue. | Anyone — read-only apart from the skip cascade. |
| `pdlc post write` | Publish a reviewed Product artifact at `Product / Approval Required`; create a new parent work item and stamp `Slug`, or replace the three Product-owned sections on an existing record. A record already at `Product / Approval Required` is re-authored in place — the gate is reset to `Stale` in the same call, no comment. | `pdlc-write`. |
| `pdlc post tasks` | Validate a UI section or a whole task breakdown against the parent record, land it, and publish the stage at `Approval Required`. A non-dry-run call on a record already at `<stage> / Approval Required` re-authors it in place, resetting the gate to `Stale` first, no comment. | `pdlc-tasks`. |
| `pdlc post plan` | Validate plan fragments against the task tree, post each as a `## Technical Plan` comment on its delivery task (never touching the body), and publish Technical Plan at `Approval Required`. A non-dry-run call on a record already at `Technical Plan / Approval Required` re-authors it in place, resetting the gate to `Stale` first, no comment. | `pdlc-plan`. |
| `pdlc post implement-task` | Submit and register one task's stacked PR, post its `## Implementation` evidence comment, and optionally close it. Never touches the human-authored task body. | `pdlc-implement`. |
| `pdlc post implement` | Resolve the current top task PR, register its number on the record, then post Implementation evidence and set `Review Required`. | `pdlc-implement`. |
| `pdlc post attach-pr` | Attach a pull-request number to a delivery task so later stages read the task's PRs explicitly. Idempotent. | `pdlc-implement`, or a driver. |
| `pdlc post test` | Resolve the current branch's PR and register it on the record, append the `--traceability` map under `## Traceability`, post Testing evidence, and set `Review Required`. | `pdlc-test`. |
| `pdlc post review` | Record a structured `PDLC-REVIEW` with `Changes Required`, `Decision Required`, or `Pass`. A clean Implementation review lands `CI Pending` and is reconciled against the PR checks in the same call. A clean Testing review on a record with 1–3 recorded Verification rework bounces skips the human step (`PDLC-AUTOAPPROVED`) and lands `Verification / Pending`. | `pdlc-review`. |
| `pdlc post ci` | Reconcile an `Implementation / CI Pending` record against its registered PRs' live check rollup: green (or no checks) → `Approval Required` (or, on a record reworked 1–3 times, straight to `Testing / Pending` with `PDLC-AUTOAPPROVED`), red → `Changes Required` with a `PDLC-IMPLEMENTATION` note, still running → no change. Mechanical, no identity check. | The autonomous loop, or a driver resuming a `CI Pending` record. |
| `pdlc post decision` | Close an `Implementation`, `Testing`, or `Verification` `Decision Required` gate from a manifest of per-decision outcomes: create a `Product / Pending` work item for each deferral, post every outcome under one `PDLC-RESOLUTION` comment, and set `Changes Required`. | Driver instruction only. |
| `pdlc post verify` | Post a structured Verification `PDLC-REVIEW`, file deferrals into Open Questions, and set the gate from `--recommendation` (`Approval Required` / `Changes Required` / `Decision Required`, the last requiring a `--decision` file of `## Decision Required` blocks posted under `PDLC-DECISION`). With `--bounce STAGE` a `Changes Required` review records `bounce` and `loop` metadata and returns that upstream stage to `Stale`, no driver step. | `pdlc-verify`. |
| `pdlc post approve` | Record human approval, advance to the next stage. | Driver instruction only. |
| `pdlc post skip` | Pre-declare skipped stages. | Driver instruction only. |
| `pdlc post invalidate` | Return a stage to `Stale`. | Driver instruction only. |
| `pdlc post complete` | Validate the structured completion evidence body (Shipped, Verification, Decisions, Open Questions, Limitations, Skipped Stages — each Open Questions entry dispositioned Resolved/Deferred), post it, lock the record, and blank the settled `## Open Questions` section to a pointer. The only parent-body edit at completion. | Driver instruction only. |
