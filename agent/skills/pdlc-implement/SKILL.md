---
name: pdlc-implement
description: "Use when asked to implement, continue, or complete a PDLC record's delivery tasks."
argument-hint: "Parent work item number to implement"
---

# Implement PDLC tasks

This skill does not implement anything itself. It confirms one PDLC record is due for implementation, resolves the driver's requested scope to a dependency-ordered list of eligible tasks, and dispatches each in turn to `swift-pro` (CORE) or `swiftui-pro` (UI) — whichever the task's own `[UI]`/`[CORE]` tag names — with a fully self-contained brief. It validates each task, has it independently reviewed at `task` depth, records the outcome, and keeps going through the rest of the requested scope in the same pass rather than stopping after one task. It never reviews its own work — every task's review is delegated to `pdlc-implementation-reviewer`. Neither `swift-pro` nor `swiftui-pro` knows anything about the PDLC pipeline — give each only what it needs to implement the code, never a pointer to "figure out the PDLC conventions" itself.

Read `../pdlc/references/parity-contract.md` before dispatching. This skill records each task's `task`-depth review outcome in that task's `## Implementation` note, but never sets a PDLC gate to `Approved` — the stage-level review outcome stays with `pdlc-review`.

When implementation or validation produces local files, pass each one to the
relevant `pdlc post implement-*` command as
`--attachment PATH [--attachment-description TEXT]`. Repeat `--attachment PATH`
for multiple files; a description applies only to the immediately preceding
file. See [PDLC attachments](../pdlc/references/attachments.md).

## Required input

Require an exact parent work item number. Check the current conversation for an unambiguous one before asking; never infer it from the branch, recent files, open PRs, or history alone.

The driver may also scope the run:

- **A named task** ("do TASK-004 next") — carry it into Step 3 as an override instead of auto-selecting; the run covers that one task only.
- **A phase** ("just the UI tasks", "the CORE tasks") — the run covers every eligible task of that phase, dependency-ordered.
- **Nothing named** — the default scope is **all** eligible tasks, CORE and UI alike, dependency-ordered. Carry the run forward until that whole scope is closed, blocked, or exhausted; do not stop after the first task just because more remain.

---

## Step 1: Resolve the record and confirm the stage

```bash
pdlc inspect WORK_ITEM
```

Returns the work item, raw work item body, and the delivery task tree Step 3 reads (metadata only, no bodies yet). No item or an ambiguous match is a hard stop.

Read `# Due Next` rather than re-deriving whether implementation is due. Require `pdlc-implement` as the owner; anything else means implementation isn't due — stop, report `Due Next` verbatim, name the actual owner.

## Step 2: Handle the gate

`Pending` (normal state for this stage), `Changes Required` (a reviewer found something in the completed implementation — read `pdlc inspect timeline WORK_ITEM`, that's this pass's scope), and `Stale` (upstream intent changed — reconcile against it) are the only gates that reach this step; `# Due Next` already stopped anything else in Step 1.

Implementation is the one stage that stays at `Pending` across many passes, potentially many tasks each. Do not try to move the gate after each task — only Step 6, once every delivery task on the whole record is closed, moves it.

## Step 3: Resolve the scope and select the next task

Step 1's `# Tasks` section carries the whole tree, classified by `taskId`, state, `isUI`, `hasPlan`/`hasImplementation`/`needsPlan`. `hasImplementation` is true when the delivery task already carries a `## Implementation` comment — never scan comments for it yourself, read the flag. Do not re-derive these by reading bodies.

A task is mechanically **eligible** when `completed: false`, `hasPlan: true`, `hasImplementation: false`. Narrow to that shortlist, then to the driver's requested scope (a named task, a phase's `isUI` value, or everything). Fetch each remaining candidate's full body:

```bash
pdlc inspect task DELIVERY_TASK [DELIVERY_TASK ...]
```

For each, confirm the two things the tree cannot tell you, by reading the body and the record's own comments:

- Every task it depends on is closed, proven by its Result and current source — not by a ticked checkbox.
- If it is classified HITL, the driver's approval for it is recorded on the record. Never dispatch a HITL task on inferred approval.

If the driver named a task, verify it is eligible by those same rules and stop with the reason if not — a named task is the whole scope. Otherwise select the first eligible task within scope, in dependency order — a UI task never gets picked ahead of a CORE task it depends on.

Dispatch **one** task at a time — never batch multiple into one agent call. After Step 5 records that task's result, return here: if the requested scope still has an eligible task, select the next one and keep going in the same pass. Stop the loop and move to Step 6 only when nothing eligible remains within scope.

If no task is eligible but open tasks remain in scope, note what's blocking them, skip past them, continue with whatever else is eligible. Stop entirely and report instead of dispatching when the task graph is incomplete, a plan contradicts current source, acceptance criteria are ambiguous, or the work needs a new product, architecture, safety, or UX decision.

## Step 4: Dispatch `swift-pro` or `swiftui-pro`

Check `git status --short` first and preserve all unrelated staged, unstaged, and untracked work.

Spawn exactly one agent for this task — `swiftui-pro` when `isUI` is true, `swift-pro` otherwise. Build its prompt from [`references/task-implementation-prompt.md`](references/task-implementation-prompt.md), filling every placeholder from the task body, its `## Technical Plan` comment, the covered requirement text, and the upstream dependency summaries. The run shares one PR across every task and that PR is this skill's responsibility — the template already tells the agent not to push, branch, or touch a pull request.

Wait for it to return before inspecting or changing its files, and before dispatching the next task in scope. Never run a second agent against the same task concurrently.

## Step 5: Validate, review, then record the result on the task

After it returns:

1. Inspect its commit against the task's plan, acceptance criteria, and the approved requirements it covers. Confirm exactly one commit touching only this task's owned files.
2. Run proportionate validation you did not author: `git diff --check`, targeted diagnostics, existing focused tests, and the affected build unless the driver limits validation.
3. **Task-level review.** Spawn `pdlc-implementation-reviewer` at `task` depth, building its prompt from `references/task-review-prompt.md` — fill every placeholder from the task body, its `## Technical Plan`, and `git show` for the commit. It is read-only and returns findings plus a verdict.
   - `Changes Required` → hand the findings back to the same `swift-pro`/`swiftui-pro` agent as its next dispatch (Step 4), telling it to amend its single commit. Re-review the amended commit. If a second review pass still returns `Changes Required`, stop the run and report the open findings to the driver — do not close the task or move to the next one.
   - `Approval Required` → continue. Non-blocking findings you accept as-is are carried into the evidence note, not silently dropped.
4. Push the commit. The run shares one pull request across every task: if none is open against the parent work item yet, open it now, linking the parent work item and noting it will accumulate every closed task's commit; if one is already open, the push lands on it — never open a second one. Do not gate on the PR's checks here — CI is reconciled after the stage review, at the `CI Pending` gate.
5. Write a summary of what was done for the task, following the outline in [`references/implementation-summary.md`](references/implementation-summary.md). This is a comment on the delivery task; **the task body is never edited** — its approved `## Technical Plan` comment and everything the Tasks stage wrote stay untouched.
6. Post the summary and close the task, in one call — the `task`-depth review passed and local validation is clean, so the task is done for this pass:

   ```bash
   pdlc post implement-task DELIVERY_TASK - --close <<'EOF'
   <summary from references/implementation-summary.md>
   EOF
   ```

Never write implementation notes into the parent work item body — task evidence belongs on the task. Return to Step 3 for the next task in scope rather than stopping here.

## Step 6: Publish only when every task is closed

The parent stays at `Implementation / Pending` while any delivery task is open. That is deliberate: it stops testing and verification from starting before the record's whole task graph is done, not just this run's scope.

If open tasks remain outside this run's scope, or something in scope was blocked or stopped early, stop here and report exactly what landed, what's still open, and why. The driver — or the loop — dispatches the rest.

You do **not** wait for CI here. The task commits are already pushed, so CI is running; the Implementation stage review (`pdlc-review`) runs against the code while checks are in flight, and the `CI Pending` gate after that review is what reconciles the outcome — `pdlc post ci` advances to `Approval Required` on green and drops to `Changes Required` (with a `PDLC-IMPLEMENTATION` note) on red. Publish once the task graph is closed. The one exception: if CI has *already* failed on commits from this run by the time you publish, dispatch the owning task's agent to fix it on the shared PR first rather than publishing a known-red implementation.

Only when **every** delivery task on the whole record is closed:

```bash
pdlc post implement WORK_ITEM - <<'EOF'
Result: all 7 delivery tasks closed; shared PR #148 is ready for review.
Exceptions: none; CI is in flight.
EOF
```

`pdlc post implement` first verifies the shared PR exists and is linked to the parent work item, then refuses this while any delivery task is open, posts the evidence, and sets `Review Required` in one step. Leave the shared PR open — merging it is a driver/review decision, not this skill's. The stage review then lands `CI Pending`, and `pdlc post ci` reconciles the checks — a red result routes back here at `Changes Required`.

## Requirement corrections

Do not silently work around a requirement, constraint, plan, or acceptance criterion that is factually wrong. A mechanically provable error — a renamed type, a dead path — may be corrected in place, with every affected reference updated. Anything that changes approved intent needs the driver: stop, report it, and let them run `pdlc post invalidate` against the owning stage. Never edit the approved specification to match what was built.

## Step 7: Report

Report only the requested scope, blocked/skipped tasks, material exceptions, PR/check state, and current `Status`/`Gate State`. Do not repeat per-task files or routine green validation already recorded on the task comments. If published, say it is at `Review Required`; after review, Implementation may park at `CI Pending` until checks settle.

Never set `Approved` and never continue into Testing.

---

## Boundaries

- Do not author tests — `pdlc-test` owns coverage. `swift-pro`/`swiftui-pro` are instructed not to create, edit, or delegate tests as part of a task.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete` — driver-only.
- Do not edit the parent's `Product`, `UI`, `Decisions`, or `Open Questions` sections.
- Do not write lifecycle state into any work item body — those fields are script-owned.
- Never mix a CORE and a UI task in the same agent dispatch, even when both are in scope.
- Never close a task before its `task`-depth `pdlc-implementation-reviewer` pass returns `Approval Required`.
- Keep the `task`-depth review shallow — it is `pdlc-implementation-reviewer` with `references/task-review-prompt.md`, not `trailnest-ultra-review` and not a stage-level review.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim delegated implementation, build, test, PR, or check evidence that does not exist.
- Do not create or switch branches — assume the current branch is correct.
- Do not open more than one pull request per run; every task's commit lands on the one shared PR.
- Do not merge the shared PR — that is a driver/review decision.

## Checklist

Each run:

- [ ] Resolved the record with `pdlc inspect`, and `Status` is `Implementation`
- [ ] `Gate State` was `Pending`, `Changes Required`, or `Stale`
- [ ] Scope resolved (named task, phase, or all) before selecting anything
- [ ] Every dispatched task was eligible by plan, dependencies, and HITL approval
- [ ] Each task went to `swiftui-pro` or `swift-pro` per its own `isUI` tag, one task per dispatch
- [ ] Dependencies proven by Result and current source, not ticked boxes
- [ ] Each dispatched task made exactly one commit on the current branch, no branch created, no PR opened by the sub-agent
- [ ] Validation actually run per task before its `task`-depth review
- [ ] Each task passed a `task`-depth `pdlc-implementation-reviewer` review before its commit was pushed
- [ ] A review `Changes Required` looped back to the implementing agent; a second failure stopped the run
- [ ] `## Implementation` comment posted on each task via `pdlc post implement-task`, recording the review outcome; the task body left untouched
- [ ] Each reviewed task closed and the run moved straight on to the next in scope
- [ ] Published once the task graph closed without waiting on CI; only an already-red check from this run was fixed first
- [ ] The run continued through the rest of its scope rather than stopping after one task
- [ ] Parent left at `Implementation / Pending` unless every delivery task is closed
- [ ] Published exactly once, and only after the last task closed
