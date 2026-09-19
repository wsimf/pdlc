---
name: pdlc-implement
description: "Use when a resolved PDLC work item has Implementation due. Runs the loop `pdlc inspect implement` drives: the next task, PR-comment and CI fixes, change-request triage, and the stage publish."
argument-hint: "Parent work item number to implement"
---

# Run the Implementation loop

`pdlc inspect implement` names one unit of work per call: a task to implement, a task to fix, or the change requests to triage. Do that unit, land it with the command the output's `## Publish` section names, and run it again; the loop ends when it names the stage publish or says what it is waiting on. The task's implementer sub-agent writes the code, `pdlc-implementation-reviewer` checks it at `task` depth, `pdlc-test-writer` adds unit coverage for what each unit changed, and `pdlc post implement-task` lands each unit. This skill owns orchestration; it never decides the code's content.

The sub-agents know nothing about the PDLC pipeline, so every brief this skill builds must stand on its own.

Read `pdlc guide contract` when resolving lifecycle questions. Use [`references/task-implementation-prompt.md`](references/task-implementation-prompt.md), [`references/fix-pr-comments.md`](references/fix-pr-comments.md), [`references/task-review-prompt.md`](references/task-review-prompt.md), [`references/task-test-prompt.md`](references/task-test-prompt.md), [`references/triage-prompt.md`](references/triage-prompt.md), and [`references/implementation-summary.md`](references/implementation-summary.md) as templates.

## Resolve

Require the exact parent work-item number from the conversation. If it is missing or ambiguous, stop and ask; never infer it from a title, branch, file, PR, or history.

Run:

```bash
pdlc inspect implement WORK_ITEM
```

`## Readiness` says whether this skill owns the record right now. Not ready means another owner, a human boundary, or a blocker: report the line verbatim and stop. A `Decision Required` gate is a human boundary; point the driver at `pdlc guide decisions`. A skipped stage, malformed record, unavailable workflow, or backend error is a blocker.

Carry the driver's follow-up verbatim. This step is complete when the record is ready and the driver's follow-up, if any, is in hand.

## Loop

Each pass starts from the latest `pdlc inspect implement` output. Read `## Mode`, then take the unit under the mode's heading below. Before dispatching a task, confirm from its body and the record's comments that every task it depends on is closed, proven by its Result and current source rather than its state alone, and that a `HITL` task has the driver's recorded approval, never an inferred one. After Land, re-run `pdlc inspect implement WORK_ITEM` and take the next pass; a `triage` pass ends in Publish instead, since its requests stay open until the stage publishes. Never predict the next unit from the last one, and never skip a unit because you would have picked another; the output is the queue.

Stop and report instead of dispatching when one of those checks fails, the plan contradicts current source, acceptance criteria are ambiguous, or the work needs a new product, architecture, safety, or UX decision.

Every unit that touches a task follows the same mechanics; only the brief differs:

1. **Task.** `pdlc inspect task DELIVERY_TASK` renders the task's front matter, full body with acceptance criteria, `## Technical Plan`, and `## Agent`, the implementer sub-agent this project routes the task to.
2. **Branch.** Check `git status --short`; the tree must be clean, with all unrelated staged, unstaged, and untracked work preserved. Then `pdlc checkout DELIVERY_TASK`, which puts you on that task's branch whether it exists yet or not; never hand-roll a branch or a base.
3. **Dispatch** the agent `## Agent` names, and only that one, with the mode's brief. The templates have the agent commit on the current branch and never push; the branch and PR stay with this skill and the CLI.
4. **Wait** for it to return before touching its files.
5. **Check the result**, mechanically only: the tree is clean, the new commits sit on the task branch and touch only this task's owned files, and the report names the validation it ran. Judging the code is Review's job, not this skill's; for a red-check fix, the reproducing command passing is part of the report, since the check is the unit's done signal.

The dispatch is complete when its work is committed on the task branch with a clean tree and its report is in. Then continue with the mode's remaining steps.

### `implement`

The unit is the task under `## Next Task`; the branch is new or, for a Stale task, already holds its landed code.

1. Dispatch with [`references/task-implementation-prompt.md`](references/task-implementation-prompt.md), filling every placeholder from the task body, its `## Technical Plan`, the covered requirement text, the upstream dependency summaries, and `pdlc inspect capability build-run --name`. A Stale task's `reconcile:` line and `#### Invalidation` fill the findings section; omit that section otherwise. When the project configures a build-run capability, the prompt also has the agent build, run, and verify the task's acceptance criteria against the running app before it commits, fixing what it finds; the template says how to tell and what to drop when it does not.
2. Review.
3. Test.
4. Land.

### `rework`

The unit is the task under `## Next Fix`; the branch already holds its landed code, and the fix lands as new commits on top.

1. Dispatch with the unit's own text as the brief. `#### Unresolved threads` use [`references/fix-pr-comments.md`](references/fix-pr-comments.md), with `#### Decisions` pasted into its `## Decisions` section. `#### Failing checks` are classified with [`references/fix-ci.md`](references/fix-ci.md) first, and each code cause fills the findings section of [`references/task-implementation-prompt.md`](references/task-implementation-prompt.md). A fix with both starts with the threads prompt and names the check causes under it.
2. Review.
3. Test, scoped to the threads, checks, and findings the fix addressed.
4. Land.
5. Escalate, when the agent skipped any thread.

### `triage`

`## Open Requests` prints every open change request in full and the task stack under `#### Stack`. The requests are the whole record's; the implementer decides which task each finding belongs to with the code in front of it, and one publish pushes every branch:

1. **Task.** `pdlc inspect task` for every task in the stack, for its `## Technical Plan`, and for the top task's `## Agent`.
2. **Branch.** Check `git status --short`; the tree must be clean. Then `pdlc checkout TOP_TASK`, which puts you on the top branch with every task branch of the stack local.
3. **Dispatch** the top task's agent once with [`references/triage-prompt.md`](references/triage-prompt.md), filling the requests verbatim and the stack with each task's branch and plan. The brief has it place each finding on its owning task's branch, lowest first, fall back to the top branch when ownership is unclear or a fix depends on a lower one, commit per branch, and never push, rebase, or amend. A finding that needs a product, architecture, UX, safety, or scope call, or that would change what a task was specified to do, stops it: report that finding with the request's link and stop; a finding that changes approved intent follows Requirement corrections.
4. **Wait**, then **check the result** as in the shared mechanics: every branch it names is clean, its commits are on the branches its report says, and the report gives each finding a disposition.
5. Review, over every commit the agent made, with the requests as the criteria to trace.
6. Test, on the top branch, with each fixed finding under `## What changed`.
7. Publish. The evidence carries the agent's report: every finding with its request, disposition, branch, and commit.

The pass is complete when every finding is fixed and committed on its branch, noted as already met, or has stopped the run, and Publish has pushed the stack.

### `none`

Nothing to work. Run Publish.

## Review

Dispatch `pdlc-implementation-reviewer` at `task` depth with [`references/task-review-prompt.md`](references/task-review-prompt.md), filling every placeholder from the task body, its `## Technical Plan`, and `git log`/`git show` for the dispatch's commits. For a fix, the criteria to trace are the findings it addressed. It is read-only and returns findings plus a verdict; this is a shallow task pass, not the stage review `pdlc-review` owns.

On `Changes Required`, hand the findings verbatim to the same implementing agent. The fix is new commits on top, never an amend or rebase, so the history of what the reviewer asked for stays legible; review it again. On `Approval Required`, carry every non-blocking finding you accept into the summary. After a third `Changes Required`, stop and report the open findings. This step is complete when the task-depth review returns `Approval Required` within three passes.

## Test

Dispatch `pdlc-test-writer` once with [`references/task-test-prompt.md`](references/task-test-prompt.md), filling every placeholder from the task body, its `## Technical Plan`, the diff of the implementer's commits, its report-back and the threads, checks, or findings it addressed under `## What changed`, and the test capabilities it names; the brief scopes the agent to this task's unit coverage and to what this dispatch changed, since whole-feature acceptance coverage belongs to `pdlc-test`. It commits onto the same task branch and does not push. This step is complete when its report is in and the commit(s) it added are on the task branch.

## Land

Write the summary to a local file following [`references/implementation-summary.md`](references/implementation-summary.md), then run the command `## Publish` printed for this unit:

```bash
pdlc post implement-task DELIVERY_TASK /tmp/pdlc-task-summary.md
```

Pass any local files implementation or validation produced, or the driver supplied, with `--attachment PATH`; see `pdlc guide attachments`.

The command records the summary as the task's `## Implementation` comment and as its PR's description, leaves the task body untouched, closes the task when it was open, and re-lands it when it was closed. A failure posts no comment and changes no state, so the next `pdlc inspect implement` offers the same unit again; report the exact error. If the PR exists but the run failed before `prs` came back, register it with `pdlc post attach-pr DELIVERY_TASK PR_NUMBER` (idempotent), then re-run `pdlc post implement-task`. This step is complete when the JSON shows this task's `taskPr`; for a re-land, `openThreads` must be `0` or equal the threads the agent reported as skipped. Any other open thread goes back to the same agent once, then is reported. Skipped threads go to Escalate.

## Escalate

A thread the agent skipped, as invalid or as diverging from the agreed plan or acceptance criteria, is the driver's call, not this skill's. Land the other fixes first, then park the record:

```bash
pdlc post escalate WORK_ITEM /tmp/pdlc-implement-decision.md
```

The evidence carries a `## Decision Required` section with one block per skipped thread, in the layout `pdlc guide decisions` reads: a `###` label naming the thread, then `Question` (the reviewer's ask in one sentence, with the thread's link), `Options` (apply it; close the thread as not applicable; change the plan), `Recommendation` (the agent's response verbatim: invalid or out of scope, and why), `Blocks` (the task), and `Why not mechanical`. Open the section by telling the driver how each option is carried out: close the thread on GitHub when the comment does not apply; leave it open to have it implemented on the next pass, in which case the answer may say how; and change the plan through `pdlc post invalidate` when the comment is right about the plan being wrong. Leave the threads untouched yourself: no reply, no resolution. The command halts the loop at `Decision Required`; report it and stop.

When the driver answers, the next `pdlc inspect implement` offers the same unit with the resolution under `#### Decisions`. A thread named there that is still open is approved: the fix brief carries the resolution, and the agent implements that thread whatever its earlier judgement was.

This step is complete when the JSON shows `gateState: Decision Required` and the report names every escalated thread.

## Publish

`mode: none` ends the loop. `## Publish` either names `pdlc post implement`, or says what it is waiting on, such as pending checks or unplanned tasks: report that and stop.

Write the stage evidence to a local file, or pass a short one as `text:<body>`: the result, the task PR stack, any exception, and, after a triage, each request and how it was addressed (the owning task and fix commit, or already met by current source).

```bash
pdlc post implement WORK_ITEM /tmp/pdlc-implement-evidence.md
```

The command pushes the whole stack first, so any commit still local on a task branch reaches its PR here; a push failure changes no state. It refuses while any delivery task is open. On success every open PR in the stack is ready for review and the JSON returns the registered `pullRequest`; a failure leaves the stage unpublished, so a re-run is clean. Leave the stack unmerged; merging is a driver decision. This step is complete when the JSON shows `gateState: Review Required`.

## Report

Relay the command JSON, plus, for each pass:

- the mode, the task, and its `taskPr`;
- the task-depth review verdict and pass count;
- for a new task, the acceptance criteria verified against the running app and their outcome;
- for a fix, the threads, checks, or findings it addressed, and any thread escalated with its justification;
- the unit coverage added;
- any material exception or accepted non-blocking finding.

Then the final `Status`/`Gate State` and what ended the loop. Leave per-task files and routine green validation on the task comment. The report is complete when it contains every pass, the final gate, and every unresolved failure or risk.

## Requirement corrections

Surface a requirement, constraint, plan, or acceptance criterion that is factually wrong rather than working around it. Correct a mechanically provable error, such as a renamed type or a dead path, in place, updating every affected reference. Anything that changes approved intent goes to the driver: stop, report it, and name `pdlc post invalidate` against the owning stage. The approved specification stays as approved, even where the build differs.

## Boundaries

- Keep code with the `## Agent` implementer, review judgement with `pdlc-implementation-reviewer`, and unit coverage with `pdlc-test-writer`; this skill writes no code and authors no acceptance tests.
- Use the CLI as the only work-item interface; lifecycle state, evidence markers, and the parent's Product, UI, Decisions, and Open Questions sections belong to other owners.
- Branches come only from `pdlc checkout`, and PRs only from `pdlc post implement-task`; keep task work off the base branch and other tasks' branches, and leave pushing, rebasing, and merging to those tools and the driver.
- Claim only implementation, build, test, PR, or check evidence that exists.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`; those are driver actions. The stage ends at `Review Required`, never `Approved` or Testing.
- Do not run `pdlc post review`; verdicts belong to `pdlc-review`. The only gate this skill sets besides its own publish is `Decision Required`, through `pdlc post escalate` from Escalate, for a thread the agent skipped.
- Preserve unrelated staged, unstaged, and untracked work.
