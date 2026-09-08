---
name: pdlc-implement
description: "Use when asked to implement, continue, or complete a PDLC record's delivery tasks."
argument-hint: "Parent work item number to implement"
---

# Implement one PDLC task

**One invocation implements exactly one delivery task**, then stops. `pdlc-loop` or the driver re-invokes it for the next.

This skill writes no code and reviews none of its own work — it dispatches both and records the outcome. It never sets a gate to `Approved`, never authors acceptance tests, and never continues into Testing; those belong to `pdlc-review` and `pdlc-test`. The sub-agents it dispatches to know nothing about the PDLC pipeline, so every brief it builds must stand on its own.

If the lifecycle rules are not already clear to you, read `../pdlc/references/parity-contract.md` before dispatching.

When implementation or validation produces local files, or the driver supplied local files in this prompt, pass each one to the relevant `pdlc post implement-*` command as `--attachment PATH [--attachment-description TEXT]`. Repeat `--attachment PATH` for multiple files; a description applies only to the immediately preceding file. See [PDLC attachments](../pdlc/references/attachments.md).

---

## Step 0: Check

Require an exact parent work item number. Check the current conversation for an unambiguous one before asking; never infer it from the branch, recent files, open PRs, or history alone. The driver may scope the run further — "do TASK-004 next" is `--task TASK-004`, "just the UI tasks" is `--phase ui`. Either way the run covers **one** task.

```bash
pdlc inspect implement WORK_ITEM [--task TASK-NNN | --phase core|ui]
```

Fail fast here. Everything below reads a section of that output.

**`## Readiness`** — implementation is due only at Status `Implementation`, gate `Pending`, `Changes Required`, or `Stale`, and not skipped. Anything else → stop, report the line verbatim, name the owning stage. The three gates that do reach you differ:

- `Pending` — normal. Implement the next task.
- `Changes Required` — a reviewer found something in the completed implementation. Read `pdlc inspect timeline WORK_ITEM`; those findings are this run's scope.
- `Stale` — upstream intent changed. Reconcile the task against it before implementing.

Implementation stays at `Pending` across every task. Do not move the gate here — Step 4 moves it, and only once every delivery task on the record is closed.

**`## Next Task`** — the single eligible task (OPEN, technically planned, not yet implemented), with its `## Technical Plan` inline, its `branch:`, and the `stackSetup:` command. This is the task, whether or not you would have picked it: the order is CORE before UI, then task number, and `--task` / `--phase` only narrow the scan. Nothing eligible → report `## Remaining` and stop; the record is waiting on planning, or on tasks outside this run's scope.

**`## Judgment Required`** — what the script cannot decide. Settle every line before dispatching, from the task body and the record's own comments: a dependency counts as closed only when its Result and current source say so, and a HITL task needs the driver's recorded approval, never an inferred one.

Stop and report rather than dispatching when any of those fails, when the plan contradicts current source, when acceptance criteria are ambiguous, or when the work needs a new product, architecture, safety, or UX decision.

**`## Remaining`** — the rest of the record, for your final report.

## Step 1: Implement

```bash
pdlc inspect task DELIVERY_TASK
```

This is the task's own record: front matter (`isUI`, `hasPlan`, `prs`), the full body with its acceptance criteria, its `## Technical Plan`, and `## Agent` — the implementer sub-agent this project routes this task to, resolved from its `isUI`. Dispatch to exactly that agent; do not pick one yourself.

1. **Branch.** Check `git status --short` and preserve all unrelated staged, unstaged, and untracked work — the tree must be clean before you branch. Then run Step 0's `stackSetup:` line verbatim: it is the code host's own stack vocabulary, and hand-rolling the branch or its base breaks it. A `Changes Required` re-run needs no new branch — `gh stack checkout <branch>` puts you back on it, and the fix lands as a new commit on top.
2. **Dispatch one agent.** The one `## Agent` names, and only one — never mix a CORE and a UI task in a single dispatch, and never run two agents against the same task concurrently. Build its prompt from [`references/task-implementation-prompt.md`](references/task-implementation-prompt.md), filling every placeholder from the task body, its `## Technical Plan`, the covered requirement text, and the upstream dependency summaries. The template tells it to make exactly one commit on the current branch and not to push, branch, or touch a pull request — the branch and the checkpoint are this skill's job.
3. **Wait** for it to return before inspecting or changing its files.
4. **Inspect the commit** against the task's plan, acceptance criteria, and the approved requirements it covers. Confirm the dispatch produced exactly one commit, touching only this task's owned files.
5. **Validate what you did not author**: `git diff --check`, targeted diagnostics, existing focused tests, and the affected build unless the driver limits validation.

## Step 2: Review

Spawn `pdlc-implementation-reviewer` at `task` depth, building its prompt from `references/task-review-prompt.md` — fill every placeholder from the task body, its `## Technical Plan`, and `git show` for the commit. It is read-only and returns findings plus a verdict. Keep this shallow: it is a task-depth pass, not the stage-level review `pdlc-review` owns.

- `Changes Required` → hand the findings back to the same implementing agent as its next dispatch. The fix is a new commit on top, never an amend or rebase of the first — the history of what a reviewer asked for stays legible. Re-review it. If a second pass still returns `Changes Required`, stop and report the open findings — do not checkpoint the task or advance.
- `Approval Required` → continue. Non-blocking findings you accept as-is are carried into the evidence note, not silently dropped.

Never checkpoint a task whose `task`-depth review has not returned `Approval Required`.

## Step 3: Test

Spawn `pdlc-test-writer` once, scoped to this task only — its plan, its acceptance criteria, and the commit's diff — for unit-level coverage of the code just shipped. It commits onto the same task branch. Whole-feature acceptance coverage is not this skill's job; that is the Testing stage. Wait for its report and re-inspect the commit(s) it added.

## Step 4: Checkpoint and publish

Write a summary following [`references/implementation-summary.md`](references/implementation-summary.md), then land it. It is a comment on the delivery task; **the task body is never edited**, and implementation notes never go into the parent work item body.

```bash
pdlc post implement-task DELIVERY_TASK - --close <<'EOF'
<summary from references/implementation-summary.md>
EOF
```

This runs `gh stack sync --prune` and `gh stack submit --auto` to rebase the stack, drop members whose PR has landed, and create or update one pull request per branch, then registers this task's PR number on the task, posts the `## Implementation` comment, and closes the task. When it succeeds, the task PR is titled with this task's title and described by the summary above, `taskPr` holds this task's PR and `prs` its registered numbers. A failure short of that leaves no comment and no closure — `pdlc inspect implement` still offers the task and a re-run is clean. It does **not** gate on that PR's checks; CI is reconciled after the stage review, at the `CI Pending` gate.

If the stack submit opened or updated the PR but the run failed before `prs` came back — or you had to open the PR by hand — register it explicitly so later stages see it: `pdlc post attach-pr DELIVERY_TASK PR_NUMBER` (idempotent). Then re-run `pdlc post implement-task` to land the comment and closure.

**Publish only when every delivery task on the record is closed.** The parent stays at `Implementation / Pending` while any task is open — that is what stops testing and verification from starting before the whole task graph is done. Any task still open → stop and report what landed and what remains; the loop or the driver dispatches the next.

```bash
pdlc post implement WORK_ITEM - <<'EOF'
Result: all 7 delivery tasks closed; the task PR stack (#148–#154) is ready for review.
Exceptions: none; CI is in flight.
EOF
```

`pdlc post implement` refuses while any delivery task is open, registers the top task PR on the record, posts the evidence, and sets `Review Required`. Leave the stack open — merging it is a driver/review decision. The stage review then lands `CI Pending`, and `pdlc post ci` reconciles the live check rollup across every PR registered on the record and its tasks — a red result routes back here at `Changes Required`.

## Step 5: Report

Report the one task implemented, its `taskPr`, the `task`-depth review outcome, unit coverage added, any material exception, and current `Status`/`Gate State`. Do not repeat per-task files or routine green validation already on the task comment. If this was the last task and you published, say it is at `Review Required`; after review, Implementation may park at `CI Pending` until checks settle.

Never set `Approved` and never continue into Testing.

## Requirement corrections

Do not silently work around a requirement, constraint, plan, or acceptance criterion that is factually wrong. A mechanically provable error — a renamed type, a dead path — may be corrected in place, with every affected reference updated. Anything that changes approved intent needs the driver: stop, report it, and let them run `pdlc post invalidate` against the owning stage. Never edit the approved specification to match what was built.

---

## Boundaries

- Implement **one** task per invocation. Do not loop through the rest of the scope yourself — the queue or the driver re-invokes the skill.
- Do not author acceptance tests — `pdlc-test` owns whole-feature coverage. `pdlc-test-writer` in Step 3 is scoped to the single task's unit coverage only.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete` — driver-only.
- Do not edit the parent's `Product`, `UI`, `Decisions`, or `Open Questions` sections.
- Do not write lifecycle state into any work item body — those fields are script-owned.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim delegated implementation, build, test, PR, or check evidence that does not exist.
- Create the task branch only through `gh stack init`/`gh stack add`. Do not commit task work to the base branch or to another task's branch.
- Let `gh stack` and `pdlc post implement-task` manage branches and PRs — do not run `git push`, `git rebase`, or open PRs by hand.
- Do not merge any PR in the stack — that is a driver/review decision.

## Checklist

Each run:

- [ ] Resolved the record with `pdlc inspect implement`; `## Readiness` reported ready
- [ ] `Gate State` was `Pending`, `Changes Required`, or `Stale`, and the run was scoped to what that gate means
- [ ] Exactly one task selected — the inspector's `## Next Task`
- [ ] Every `## Judgment Required` line settled: dependencies closed by Result and source, HITL approval on record
- [ ] Ran the inspector's `stackSetup:` `gh stack` command on a clean tree; no hand-rolled branching
- [ ] Dispatched to the sub-agent named in the task's `## Agent` section, and only that one
- [ ] One implementation commit per dispatch on the task branch, review fixes stacked on top; no PR opened by the sub-agent
- [ ] Validation actually run before the `task`-depth review
- [ ] `task`-depth `pdlc-implementation-reviewer` returned `Approval Required` (a `Changes Required` looped back once; a second failure stopped the run)
- [ ] `pdlc-test-writer` added unit coverage for this task onto the same branch
- [ ] `## Implementation` comment posted and task closed via `pdlc post implement-task`; task body untouched; `taskPr` recorded
- [ ] Parent left at `Implementation / Pending` unless this was the last task
- [ ] Published exactly once, and only after the final task closed
