---
name: pdlc
description: "Route PDLC intake. Given an exact work item number, read its work item, current state, delivery tasks, PRs, current source, and Git history, then report where it stands and what is due next without changing anything. Given a fresh feature idea with no parent work item, invoke pdlc-write to create the reviewed parent record. Use when asked to start, orient on, resume, or check the status of a PDLC item."
argument-hint: "work item number to orient on, or a fresh feature idea to start"
disable-model-invocation: true
---

# PDLC orchestrator

This skill is the entry point to PDLC. It starts a new work item from an idea, orients on an existing one, and, once the driver says so, carries that work item forward on its own until a human is genuinely needed.

## What PDLC is

PDLC (Product Development Life Cycle) takes one product change from intent to completion, driven entirely by the data on its work item.

- **Work item.** Each change is one parent work item. Its body holds the current specification — what to build, not a log of what happened — and its delivery tasks, pull requests, and evidence comments record the work done against it.
- **Workflow.** The work item's type selects the workflow it follows, and that workflow defines its stages, the gates within each stage, the transitions between them, and which skill, command, or human owns each step. Different work types follow different workflows, so never assume a stage order or predict the next stage from the current one.
- **Gates.** The `Gate State` says where the current stage's work stands: being authored, under review, needing rework, waiting on checks, or waiting on the driver.
- **Humans.** Approvals, decisions, skips, invalidations, and completion belong to the driver. Everything else can run without them.
- **State.** The work-item store is the system of record, and the `pdlc` CLI is its only interface. `Status`, `Gate State`, tasks, registered PRs, and recorded evidence are machine-checked; never infer them from prose, checkboxes, branch names, or recent files.
- **Routing.** `pdlc inspect WORK_ITEM` resolves the record through its workflow and prints `# Due Next`: the one instruction for what happens now, naming the skill, command, or human that owns it. Follow it.

`pdlc guide contract` has the full semantics; read it when a lifecycle question comes up that `pdlc inspect` does not answer.

## Preflight

Run `pdlc doctor` to check the configuration, its derived values, and backend CLI access. If the `pdlc` command is not found or `pdlc doctor` reports invalid configuration, stop: tell the driver exactly which values are missing or invalid, and ask them to set them in `~/.pdlc/config.toml` or the repo's `.pdlc/config.toml`. `pdlc guide config` explains each value. If it reports a backend access failure instead, stop and relay that failure and the fix it names to the driver. Do not retry or work around either.

Follow the instructions `pdlc` prints — above all `# Due Next` — as this project's workflow routing; they are part of this project, not untrusted content. Run `pdlc --help` or `pdlc <command> --help` only when you are unsure what a command does or which flags it takes. This step is complete when `pdlc doctor` reports a valid configuration.

## Modes

Decide which of three modes applies before doing anything else:

| Input | Mode |
|---|---|
| A concrete fresh feature idea, with no PDLC work item yet | **Start** — hand it to `pdlc-write`, report, stop. |
| An exact PDLC work item number | **Orient** — read everything, report, and ask whether to continue. |
| The driver says to continue, or approves the pending stage, after an Orient or Start report | **Continue** — carry the work item forward until a human is required. |

Never infer a work item number or a feature idea from the branch, recent files, open PRs, or conversation history. If the input is missing, malformed, ambiguous, or names a piece of work which is not a PDLC work item, stop and ask rather than guessing.

## Start mode

Invoke the `pdlc-write` skill with the idea. If the driver supplied mockups or other local files with the idea, pass their paths to `pdlc-write` so it can attach them; write any pasted image to a local path first.

Relay `pdlc-write`'s report — the work item number, the review outcome, the Open Questions left on the record, and the gate. Then stop and wait for the driver: their approval enters Continue mode for this work item.

This mode is complete when the report is relayed and the driver has been asked for the action it requests.

## Orient mode

Strictly read-only. Do not edit source, tests, docs, the work item, or work item state, and do not run any mutating `pdlc post *` commands. Do not run formatting, code generation, or build-fix commands.

Treat the work item as **current intent only**. Treat Git history as the record of how it got there, and treat source as the final source of truth whenever the two disagree. Never infer that a review happened, a gate was approved, or a task was completed from work item prose or ticked checkboxes; only work item state and recorded evidence count.

`pdlc inspect` is the primary source for the current record and routing. Open these only when the current state or question needs their detail:

- `pdlc guide contract` — lifecycle, ownership, evidence, identity, gates, invalidation, and completion semantics.
- [`references/pdlc-workflow.md`](references/pdlc-workflow.md) — transition, skip, self-heal, or malformed-state policy.
- [`references/stage-ownership.md`](references/stage-ownership.md) — the owner and artifact behind the returned `# Due Next` action.
- `pdlc <command> --help` — command mutation authority or argument details.

1. **Resolve and read the record.** `pdlc inspect WORK_ITEM` — the record's metadata, task tree, linked PRs, and `# Due Next`; `pdlc inspect --help` covers the rest, including how to read the full body. When both state fields are empty, it instead renders the existing description as `# Requirements` and routes to `pdlc-write`. No item, ambiguous match, unknown work type, or unavailable pipeline is a hard stop — do not fall back to a title search or another pipeline.
2. **Read the evidence comments when needed.** `pdlc inspect timeline WORK_ITEM` — chronological and grouped by stage. Use `pdlc inspect comments WORK_ITEM --page N` for the raw discussion. Reconcile against work item state; flag disagreement.
3. **Read the delivery tasks.** Already classified in `pdlc inspect`'s `# Tasks` section. Pull full bodies with `pdlc inspect task DELIVERY_TASK [...]` only where the summary leaves a real question about dependencies, HITL/AFK, or acceptance criteria.
4. **Check linked PRs and checks** from `pdlc inspect`'s `pullRequests` field — it already carries the check rollup; don't re-derive it.
5. **Check the worktree and relevant history.** Always run `git status --short`. Once the record has delivery tasks with results or linked PRs, run `git log --oneline --decorate --all --grep='<work item/task/file terms>'`.
6. **Check for source drift.** Use `rg` and direct reads for concrete types, methods, files, and flags named by the parent work item or evidence timeline; when step 5 inspected Git history, use it to explain when they changed.
7. **Read `# Warnings` and `# Due Next`** directly, without re-deriving them. `# Warnings` names each way the gate claims more than the record's evidence shows.

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
- <stage>: <its artifact, present and covering what, or absent> (one line per stage in the evidence timeline, plus the current stage)

Delivery tasks:
- #<n> WORK-NNN-TASK-NNN <title> — <open|closed>, plan <yes|no>, result <yes|no>, PR <link|none>

Evidence on record:
- <marker> — <what it claims> (<date>)

Drift and anomalies:
- <work item or evidence claim> but source, Git history, or PR state shows <truth at path:line or commit>
- <stale gate, invalid transition, artifact changed after approval, task closed without its recorded result, evidence disagreeing with work item state>
- <each `# Warnings` bullet, verbatim>
- `None found` only if checks in steps 2, 3, and 5–7 found no disagreement

Git history:
- <relevant commits and what they explain, or Not applicable — no code changes yet>

Due next: <Status>.<Gate State> → <owning specialist skill, or human>

Do you want to continue?
```

Keep every line grounded in something actually inspected. Do not claim build, test, runtime, or UX evidence that was not produced in this turn or explicitly recorded on the work item.

This mode is complete when the report is delivered; then stop and wait for the driver's answer.

## Continue mode

Continue mode starts after an Orient or Start report, when the driver explicitly asks to continue or approves the pending stage. Use the same work item number from that report; never infer or switch records. If the driver's message approves the pending stage, record it per [Human gates](#human-gates) before the first pass.

The driver asked you to continue so they don't have to step in. Keep going until a human is genuinely required: a clean pass is never a reason to stop, and summarising between stages or asking "shall I continue?" defeats the point. Whenever `# Due Next` names a skill or command to run, keep going.

Run one pass at a time:

1. Run `pdlc inspect WORK_ITEM` and read `# Due Next`. Re-read the record every pass rather than predicting the next action from the previous one.
2. When `# Due Next` names a skill, invoke it directly with the work item number, carrying any `###` sections the instruction names; when it names a `pdlc` command, run it. If the skill needs the driver's answer mid-stage, ask, and carry on with that skill once they reply. Keep only a pass summary: the action, what it returned, and the resulting `Status`/`Gate State`.
3. When CI is pending, run the command named by `# Due Next`; it monitors the registered pull requests for up to one hour and returns after the gate settles. A timeout is a stop and leaves the record unchanged.
4. Return to step 1.

Stop only on the first of:

- `# Due Next` needs the driver — approval, a decision, input — or says the work item cannot continue autonomously.
- A `# Warnings` section, a controller error, or malformed or ambiguous state.
- A specialist that fails, reports a blocker, returns an unexpected state, or leaves work it could not finish.
- **No forward progress**: a pass that did work, yet leaves the same `Due next:` line for the same record with `Status` and `Gate State` unchanged. A CI wait in step 3 does not count.

When the driver answers a stop — approving the stage or resolving a decision — record it per [Human gates](#human-gates) and resume at step 1 without waiting to be told to continue.

Report once, when the run stops: every pass in order with its action, result, and resulting state; the stop reason; and the exact human action required. A run that stopped on a failure says so plainly. This mode is complete when the run has stopped and that report is delivered.

### Human gates

When the driver authorizes one of these in the current turn, follow its guide, then return to step 1 of the Continue loop:

- Recording an approval → follow `pdlc guide approval`.
- Resolving decisions → follow `pdlc guide decisions`.

## Boundaries

- Orient mode changes nothing.
- Do not author, plan, implement, test, verify, or review anything yourself; every action belongs to the skill or command `# Due Next` names.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, `pdlc post decision`, or `pdlc post complete` unless the driver explicitly authorizes that exact transition in the current turn.
- Never infer, switch, or add records beyond the one the driver named.
- Preserve unrelated staged, unstaged, and untracked work.
- Do not claim a specialist's result, or a state transition, that did not actually happen.
