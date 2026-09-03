---
name: pdlc-implement
description: "Use when asked to implement, continue, or complete a PDLC record's delivery tasks."
argument-hint: "Parent work item number to implement"
---

# Implement one PDLC task

This skill does not implement anything itself. Per invocation it confirms one PDLC record is due for implementation, resolves the **single** next eligible delivery task, dispatches it to the project's implementer sub-agent — `pdlc inspect capability ui-implementer` for a `[UI]` task, `pdlc inspect capability core-implementer` otherwise — with a fully self-contained brief, validates the commit, has it independently reviewed at `task` depth, dispatches `pdlc-test-writer` for that task's own unit coverage, and checkpoints the result as a stacked pull request. Then it stops. `pdlc-loop` re-invokes the skill for the next task; a driver runs it again by hand. It never reviews its own work — every task's review is delegated to `pdlc-implementation-reviewer`. The implementer sub-agent knows nothing about the PDLC pipeline — give it only what it needs to implement the code.

Read `../pdlc/references/parity-contract.md` before dispatching. This skill records each task's `task`-depth review outcome in that task's `## Implementation` note, but never sets a PDLC gate to `Approved` — the stage-level review outcome stays with `pdlc-review`.

When implementation or validation produces local files, or the driver
supplied local files in this prompt, pass each one to the relevant
`pdlc post implement-*` command as
`--attachment PATH [--attachment-description TEXT]`. Repeat `--attachment PATH`
for multiple files; a description applies only to the immediately preceding
file. See [PDLC attachments](../pdlc/references/attachments.md).

## Required input

Require an exact parent work item number. Check the current conversation for an unambiguous one before asking; never infer it from the branch, recent files, open PRs, or history alone.

The driver may also scope the run to one task or one phase:

- **A named task** ("do TASK-004 next") — pass it as `--task TASK-004`.
- **A phase** ("just the UI tasks") — pass it as `--phase ui` / `--phase core`; the skill still implements only the first eligible task of that phase this run.
- **Nothing named** — the skill implements the first eligible task overall, CORE before UI.

Either way the run covers **one task**. The queue, or the driver, drives the next.

---

## Step 1: Resolve the record and the next task

```bash
pdlc inspect implement WORK_ITEM [--task TASK-NNN | --phase core|ui]
```

`## Readiness` reports whether implementation is due (Status `Implementation`; gate `Pending`, `Changes Required`, or `Stale`; not skipped). Not ready → stop, report `## Readiness` verbatim, name the owning stage.

`## Next Task` names the single eligible task — OPEN, technically planned, not yet implemented — in CORE-before-UI order, with its `## Technical Plan` rendered inline, its `branch:`, and the `stackSetup:` `gh stack` command that puts that branch on the stack. Nothing eligible → report `## Remaining` and stop; the record waits on planning or on tasks outside this run.

## Step 2: Handle the gate

`Pending` (normal), `Changes Required` (a reviewer found something in the completed implementation — read `pdlc inspect timeline WORK_ITEM`, that is this task's scope), and `Stale` (upstream intent changed — reconcile against it) are the only gates that reach this step; `## Readiness` already stopped anything else.

Implementation stays at `Pending` across every task. Do not try to move the gate here — Step 7 moves it, and only once every delivery task on the whole record is closed.

## Step 3: Confirm the task is truly ready

`## Judgment Required` lists what the inspector cannot decide. Fetch the task body if you need it (`pdlc inspect task DELIVERY_TASK`) and confirm, from the body and the record's own comments:

- Every task this one depends on is closed, proven by its Result and current source — not by a ticked checkbox.
- If it is classified HITL, the driver's approval for it is recorded on the record. Never dispatch a HITL task on inferred approval.

Fails either check → stop with the reason. Stop and report rather than dispatching when the plan contradicts current source, acceptance criteria are ambiguous, or the work needs a new product, architecture, safety, or UX decision.

## Step 4: Put the task's branch on the stack, then dispatch

Check `git status --short` first and preserve all unrelated staged, unstaged, and untracked work. The tree must be clean before you branch.

Run the `stackSetup:` line Step 1 gave you, verbatim. It is one of:

```bash
# First task on the record — creates the stack on the repository's default branch.
gh stack init <branch>

# Any later task — enters the stack at the previous task's PR, then adds this branch on top.
gh stack checkout <stackEntryPr> && gh stack add <branch>
```

`gh stack` owns the stack: its order, each branch's base, rebasing onto a moved trunk, and skipping members whose PR has landed. Never compute a base branch, never `git checkout -B` off a predecessor, and never check whether a predecessor's branch still exists — `gh stack checkout <pr>` fetches the stack from GitHub even on a fresh clone, and a merged predecessor is handled by the extension.

Re-running the task for `Changes Required` is the same setup — `gh stack checkout <branch>` puts you back on it — followed by amending its single commit.

Spawn exactly one agent — resolve which with `pdlc inspect capability ui-implementer` when `isUI` is true, `pdlc inspect capability core-implementer` otherwise (each resolves to `general-purpose` when the project configures no implementer). Build its prompt from [`references/task-implementation-prompt.md`](references/task-implementation-prompt.md), filling every placeholder from the task body, its `## Technical Plan` comment, the covered requirement text, and the upstream dependency summaries. The template tells the agent to make exactly one commit on the current branch and not to push, branch, or touch a pull request — the branch and the checkpoint are this skill's job.

Wait for it to return before inspecting or changing its files. Never run a second agent against the same task concurrently.

## Step 5: Validate, review, add unit coverage, record

After it returns:

1. Inspect its commit against the task's plan, acceptance criteria, and the approved requirements it covers. Confirm exactly one commit touching only this task's owned files.
2. Run proportionate validation you did not author: `git diff --check`, targeted diagnostics, existing focused tests, and the affected build unless the driver limits validation.
3. **Task-level review.** Spawn `pdlc-implementation-reviewer` at `task` depth, building its prompt from `references/task-review-prompt.md` — fill every placeholder from the task body, its `## Technical Plan`, and `git show` for the commit. It is read-only and returns findings plus a verdict.
   - `Changes Required` → hand the findings back to the same implementing agent as its next dispatch (Step 4), telling it to amend its single commit. Re-review the amended commit. If a second pass still returns `Changes Required`, stop and report the open findings — do not checkpoint the task or advance.
   - `Approval Required` → continue. Non-blocking findings you accept as-is are carried into the evidence note, not silently dropped.
4. **Unit coverage for this task.** Spawn `pdlc-test-writer` once, scoped to this task only — its plan, its acceptance criteria, and the commit's diff — for unit-level coverage of the code just shipped. It commits onto the same task branch. Whole-feature acceptance coverage is not this skill's job; that is the Testing stage. Wait for its report and re-inspect the commit(s) it added.
5. Write a summary of what was done, following [`references/implementation-summary.md`](references/implementation-summary.md). This is a comment on the delivery task; **the task body is never edited**.

## Step 6: Checkpoint the task as a stacked pull request

```bash
pdlc post implement-task DELIVERY_TASK - --close <<'EOF'
<summary from references/implementation-summary.md>
EOF
```

With `PDLC_STACKED_PRS` enabled this first runs `gh stack sync --prune` and `gh stack submit --auto` — the extension rebases the stack, drops members whose PR has landed, and creates or updates one pull request per branch — then registers this task's PR number on the task; only then does it post the `## Implementation` comment and close the task. A stack-submit failure therefore leaves no comment and no closure — `pdlc inspect implement` still offers the task and a re-run is clean. This task's PR comes back in `taskPr` and its registered numbers in `prs`. It does **not** gate on that PR's checks; CI is reconciled after the stage review, at the `CI Pending` gate. Record `taskPr` in your report.

If the stack submit opened or updated the PR but the run failed before `prs` came back — or you had to open the PR by hand — register it explicitly so later stages see it: `pdlc post attach-pr DELIVERY_TASK PR_NUMBER` (idempotent). Then re-run `pdlc post implement-task` to land the comment and closure.

Never write implementation notes into the parent work item body — task evidence belongs on the task.

## Step 7: Publish only when every task is closed

The parent stays at `Implementation / Pending` while any delivery task is open — that is what stops testing and verification from starting before the whole task graph is done.

If any delivery task is still open, stop here and report exactly what landed (task, `taskPr`, review outcome) and what remains. The loop or the driver dispatches the next.

Only when **every** delivery task on the whole record is closed:

```bash
pdlc post implement WORK_ITEM - <<'EOF'
Result: all 7 delivery tasks closed; the task PR stack (#148–#154) is ready for review.
Exceptions: none; CI is in flight.
EOF
```

`pdlc post implement` refuses while any delivery task is open, registers the top task PR on the record, posts the evidence, and sets `Review Required`. Leave the stack open — merging it is a driver/review decision. The stage review then lands `CI Pending`, and `pdlc post ci` reconciles the live check rollup across every PR registered on the record and its tasks — a red result routes back here at `Changes Required`.

## Requirement corrections

Do not silently work around a requirement, constraint, plan, or acceptance criterion that is factually wrong. A mechanically provable error — a renamed type, a dead path — may be corrected in place, with every affected reference updated. Anything that changes approved intent needs the driver: stop, report it, and let them run `pdlc post invalidate` against the owning stage. Never edit the approved specification to match what was built.

## Step 8: Report

Report the one task implemented, its `taskPr`, the `task`-depth review outcome, unit coverage added, any material exception, and current `Status`/`Gate State`. Do not repeat per-task files or routine green validation already on the task comment. If this was the last task and you published, say it is at `Review Required`; after review, Implementation may park at `CI Pending` until checks settle.

Never set `Approved` and never continue into Testing.

---

## Boundaries

- Implement **one** task per invocation. Do not loop through the rest of the scope yourself — the queue or the driver re-invokes the skill.
- Do not author acceptance tests — `pdlc-test` owns whole-feature coverage. `pdlc-test-writer` in Step 5 is scoped to the single task's unit coverage only.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete` — driver-only.
- Do not edit the parent's `Product`, `UI`, `Decisions`, or `Open Questions` sections.
- Do not write lifecycle state into any work item body — those fields are script-owned.
- Never mix a CORE and a UI task in the same agent dispatch.
- Never checkpoint a task before its `task`-depth `pdlc-implementation-reviewer` pass returns `Approval Required`.
- Keep the `task`-depth review shallow — it is `pdlc-implementation-reviewer` with `references/task-review-prompt.md`, not a stage-level review.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim delegated implementation, build, test, PR, or check evidence that does not exist.
- Create the task branch only through `gh stack init`/`gh stack add`. Do not commit task work to the base branch or to another task's branch.
- Let `gh stack` and `pdlc post implement-task` manage branches and PRs — do not run `git push`, `git rebase`, or open PRs by hand.
- Do not merge any PR in the stack — that is a driver/review decision.

## Checklist

Each run:

- [ ] Resolved the record with `pdlc inspect implement`; `## Readiness` reported ready
- [ ] `Gate State` was `Pending`, `Changes Required`, or `Stale`
- [ ] Exactly one task selected — the inspector's `## Next Task`, or the driver's `--task`
- [ ] The task was eligible by plan, dependencies, and HITL approval
- [ ] Ran the inspector's `stackSetup:` `gh stack` command on a clean tree; no hand-rolled branching
- [ ] The task went to the `ui-implementer` or `core-implementer` capability per its own `isUI` tag
- [ ] Exactly one implementation commit on the task branch; no PR opened by the sub-agent
- [ ] Validation actually run before the `task`-depth review
- [ ] `task`-depth `pdlc-implementation-reviewer` returned `Approval Required` (a `Changes Required` looped back once; a second failure stopped the run)
- [ ] `pdlc-test-writer` added unit coverage for this task onto the same branch
- [ ] `## Implementation` comment posted and task closed via `pdlc post implement-task`; task body untouched; `taskPr` recorded
- [ ] Parent left at `Implementation / Pending` unless this was the last task
- [ ] Published exactly once, and only after the final task closed
