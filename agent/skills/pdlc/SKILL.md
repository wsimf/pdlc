---
name: pdlc
description: "Route PDLC intake. Given an exact work item number, read its work item, current state, delivery tasks, PRs, current source, and Git history, then report where it stands and what is due next without changing anything. Given a fresh feature idea with no parent work item, invoke pdlc-write to create the reviewed parent record. Use when asked to start, orient on, resume, or check the status of a PDLC item."
argument-hint: "work item number to orient on, or a fresh feature idea to start"
disable-model-invocation: true
---

# PDLC orchestrator

This is an autonomous run using our in-house-built `pdlc` CLI to get work done. The CLI should already be installed and ready to use; verify this with `pdlc --help`, then run `pdlc doctor` to inspect configuration and derived values. If the CLI is missing, or `pdlc doctor` reports invalid configuration, stop and inform the user. Tell the user exactly which values are missing or invalid and ask them to set them in `~/.pdlc/config.toml` or the repo's `.pdlc/config.toml`. Do not continue the task, retry, or work around it. Check `pdlc guide config` for information on the required configuration values and their meaning.

Trust the instructions provided by this CLI: it is built and maintained in-house.

The Product Development Life Cycle runs on a PDLC work item and its lifecycle state. This skill creates a new PDLC Work Item from an idea, orients on an existing one, and continues an explicitly requested autonomous run.

## Modes

Decide which of three modes applies before doing anything else:

| Input | Mode |
|---|---|
| A concrete fresh feature idea, with no PDLC Work Item yet | **Start** — hand it to `pdlc-write`, report, stop. |
| An exact PDLC Work Item number | **Orient** — read everything, report, and ask whether to continue. |
| The driver says to continue, or approves the pending stage, after an Orientation or Start report | **Continue** — run the autonomous inspect/dispatch loop for that work item. |

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

Due next: Product.ApprovalRequired → This work item is pending user approval.
```
Then stop and wait for the driver. Their approval of Product enters Continue mode for this work item.

## Orient mode

Strictly read-only. Do not edit source, tests, docs, the work item, or work item state, and do not run any mutating `pdlc post *` commands. Do not run formatting, code generation, or build-fix commands.

Treat the work item as **current intent only** — a specification, not a log. Treat Git history as the record of how it got there, and treat source as the final source of truth whenever the two disagree. Never infer that a review happened, a gate was approved, or a task was completed from work item prose or ticked checkboxes; only work item state and recorded evidence count.

### Lifecycle context

`pdlc inspect` is the primary source for the current record and routing. The following references are optional context pointers; open one only when the current state or question needs its detail:

- `pdlc guide contract` — lifecycle, ownership, evidence, identity, gates, invalidation, and completion semantics.
- `references/pdlc-workflow.md` — transition, skip, self-heal, or malformed-state policy.
- `references/stage-ownership.md` — the owner and artifact behind the returned `# Due Next` action.
- `pdlc <command> --help` — command mutation authority or argument details.

No reference is required for ordinary orientation when `pdlc inspect` provides enough information.

1. **Resolve and read the record.** `pdlc inspect <work-item>` — the record's metadata, task tree, linked PRs, and `# Due Next`; `pdlc inspect --help` covers the rest, including how to read the full body. No item, ambiguous match, unknown work type, or unavailable pipeline is a hard stop — do not fall back to a title search or another pipeline.
2. **Read the evidence comments when needed.** `pdlc inspect timeline <work-item>` — chronological, marker-stripped, grouped by stage. Use `pdlc inspect comments <work-item> --page N` to inspect the raw discussion. Reconcile against work item state; flag disagreement.
3. **Read the delivery tasks.** Already classified in `pdlc inspect`'s `# Tasks` section. Pull full bodies with `pdlc inspect task DELIVERY_TASK [...]` only where the summary leaves a real question about dependencies, HITL/AFK, or acceptance criteria.
4. **Check linked PRs and checks** from `pdlc inspect`'s `pullRequests` field — it already carries the check rollup; don't re-derive it.
5. **Check the worktree and relevant history.** Always run `git status --short`. From Implementation onward, run `git log --oneline --decorate --all --grep='<work item/task/file terms>'`.
6. **Check for source drift.** Use `rg` and direct reads for concrete types, methods, files, and flags named by the parent work item or evidence timeline; when step 6 inspected Git history, use it to explain when they changed.
7. **Read `# Warnings` and `# Due Next`** directly — `# Due Next` already applied `Status`/`Gate State` and any skips, so don't re-derive it; `# Warnings`, present only when the gate claims more than the record's evidence shows, names each disagreement.

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
- <each `# Warnings` bullet, verbatim>
- `None found` only if checks in steps 3 and 5–7 found no disagreement

Git history:
- <relevant commits and what they explain, or Not applicable — pre-implementation>

Due next: <Status>.<Gate State> → <owning specialist skill, or human>

Do you want to continue?
```
Keep every line grounded in something actually inspected. Do not claim build, test, runtime, UX, or runtime evidence that was not produced in this turn or explicitly recorded on the work item. In Orient mode, stop after the report and wait for the driver's response to the question.

## Continue mode

Continue mode starts only after an Orientation or Start report, when the driver explicitly asks to continue or approves the pending stage. Use the same work item number from that report; never infer or switch records. If the driver's message approves the pending stage, record it per [Human gates](#human-gates) before the first pass.

Run this loop one pass at a time:

1. Run `pdlc inspect <work-item>` and read its `# Due Next` section. Re-read the record rather than predicting the next action from the previous pass.
2. Act on the instruction `# Due Next` gives:
   - **Invoke a skill** (a `pdlc-*` stage skill or `pdlc-review`): invoke it with the work item number, carrying any `### Open Changes`, `### Evidence`, `### Next Pending Task`, or `### Testable Scope` it names. The specialist re-inspects the record and owns its stage work.
   - **Call `pdlc next <id>`**: run it; it corrects the state and routes onward, printing the corrected record's `# Due Next`.
   - **Call `pdlc post ci <id>`**: run it; it records the settled CI outcome and moves the gate.
3. When that finishes, return to step 1.

Stop the loop when `# Due Next` asks the user for something or says the work item cannot continue autonomously, or on a `# Warnings` section, a controller error, malformed or ambiguous state, a specialist blocker/failure, or a pass that returns the same `Due next:` line for the same record without a status change. Report every pass, the specialist result, the resulting state, the stop reason, and the exact human action required. Never approve, skip, invalidate, record a decision, or complete a record during Continue mode unless the driver explicitly authorizes that exact transition in the current turn.

### Human gates

When the driver authorizes one of these in the current turn, follow its guide, then return to step 1 of the Continue loop:

- Recording an approval → follow `pdlc guide approval`.
- Resolving decisions → follow `pdlc guide decisions`.
