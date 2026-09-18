---
name: pdlc-implement
description: "Use when a resolved PDLC work item has Implementation due, including the next pending task, changes-required reconciliation, and stale reopened tasks."
argument-hint: "Parent work item number to implement"
---

# Implement one PDLC task

Implement exactly one delivery task per invocation, then stop; `pdlc-loop` or the driver re-invokes this skill for the next. The task's implementer sub-agent writes the code, `pdlc-implementation-reviewer` checks it at `task` depth, `pdlc-test-writer` adds its unit coverage, and `pdlc post implement-task` lands and closes the task. Once every delivery task is closed, `pdlc post implement` publishes the stage at `Review Required`. This skill owns orchestration; it never decides the code's content.

The sub-agents know nothing about the PDLC pipeline, so every brief this skill builds must stand on its own.

Read `pdlc guide contract` when resolving lifecycle questions. Use [`references/task-implementation-prompt.md`](references/task-implementation-prompt.md), [`references/task-review-prompt.md`](references/task-review-prompt.md), and [`references/implementation-summary.md`](references/implementation-summary.md) as templates.

## Resolve

Require the exact parent work-item number from the conversation. If it is missing or ambiguous, stop and ask; never infer it from a title, branch, file, PR, or history.

Run:

```bash
pdlc inspect WORK_ITEM
```

Read the resolved `Status`, `Gate State`, and `# Due Next` with its `### Next Pending Task` and `### Open Changes`. Continue only when `Status` is `Implementation`; the Gate step below decides which gate states this skill acts on. Otherwise report the actual routing result and stop.

## Gate

Follow `# Due Next` for what to do, whatever produced that state, including a record edited outside PDLC:

- Names the Implementation stage (`Pending`): implement the next pending task.
- Says the work item needs changes (`Changes Required`): every open change request, review findings or failed checks, is this run's scope. `pdlc inspect changes WORK_ITEM` prints them in full.
- Says tasks were invalidated (`Stale`): upstream intent changed; reconcile the reopened task against the open changes before implementing it.
- Names a user decision (`Decision Required`): a human boundary. Report it, point the driver at `pdlc guide decisions`, and stop.

Any other due next result belongs to another owner (`pdlc-review`, `pdlc post ci`, or the driver's approval): report it and stop. A skipped stage, malformed record, unavailable workflow, or backend error is a blocker: report it and stop.

Carry the driver's follow-up verbatim. This step is complete when the gate, its evidence, and the exact follow-up are in hand for the dispatch.

## Scope

The driver may narrow the run: "do TASK-004 next" is `--task TASK-004`, "just the UI tasks" is `--phase ui`.

```bash
pdlc inspect implement WORK_ITEM [--task TASK-NNN | --phase core|ui]
```

`## Open Comments` reporting unresolved PR comments makes them this run's scope, ahead of any next task: follow [`references/fix-pr-comments.md`](references/fix-pr-comments.md) in place of the rest of Scope through Review, then Land, Publish, and Report.

`## Next Task` names the single eligible task and the branch it belongs on. It is the task, whether or not you would have picked it; `--task` and `--phase` only narrow the scan. When nothing is eligible and `### Open Changes` lists requests, every task they touch is closed: follow [`references/rework.md`](references/rework.md) in place of the rest of Scope through Land; it ends at Publish, then Report. When nothing is eligible and nothing is open, report `## Remaining` and stop; the record is waiting on planning, or on tasks outside this run's scope.

Settle every `## Judgment Required` line from the task body and the record's comments: a dependency counts as closed only when its Result and current source say so, and a HITL task needs the driver's recorded approval, never an inferred one. Keep `## Remaining` for the report.

Fetch the chosen task:

```bash
pdlc inspect task DELIVERY_TASK
```

It renders the task's front matter (`isUI`, `hasPlan`, `prs`), full body with acceptance criteria, `## Technical Plan`, and `## Agent`, the implementer sub-agent this project routes the task to.

Stop and report instead of dispatching when a judgment line fails, the plan contradicts current source, acceptance criteria are ambiguous, or the work needs a new product, architecture, safety, or UX decision. This step is complete when one task is chosen, every judgment line is settled, and none of those stop conditions holds.

## Implement

1. **Branch.** Check `git status --short`; the tree must be clean, with all unrelated staged, unstaged, and untracked work preserved. Then `pdlc checkout DELIVERY_TASK`, which puts you on that task's branch whether it exists yet or not; never hand-roll a branch or a base. A `Changes Required` re-run puts you back on the same branch, and the fix lands as a new commit on top.
2. **Dispatch** the agent `## Agent` names, and only that one, for this one task. Build its prompt from [`references/task-implementation-prompt.md`](references/task-implementation-prompt.md), filling every placeholder from the task body, its `## Technical Plan`, the covered requirement text, the upstream dependency summaries, the Gate evidence, and `pdlc inspect capability build-run --name`. The template limits it to one commit on the current branch; the branch and PR stay with this skill and the CLI. When the project configures a build-run capability, it also has the agent build, run, and verify the task's acceptance criteria against the running app before that commit, fixing what it finds; the template says how to tell and what to drop when it does not.
3. **Wait** for it to return before inspecting or changing its files.
4. **Inspect the commit** against the task's plan, acceptance criteria, and the approved requirements it covers.
5. **Validate what you did not author**: `git diff --check`, targeted diagnostics, existing focused tests, and the affected build unless the driver limits validation.

This step is complete when the dispatch produced exactly one commit on the task branch, touching only this task's owned files, and every validation above has run with its result noted.

## Review

Dispatch `pdlc-implementation-reviewer` at `task` depth with [`references/task-review-prompt.md`](references/task-review-prompt.md), filling every placeholder from the task body, its `## Technical Plan`, and `git show` for the commit. It is read-only and returns findings plus a verdict; this is a shallow task pass, not the stage review `pdlc-review` owns.

On `Changes Required`, hand the findings verbatim to the same implementing agent. The fix is a new commit on top, never an amend or rebase, so the history of what the reviewer asked for stays legible; validate and review it again. On `Approval Required`, carry every non-blocking finding you accept into the summary. After a second `Changes Required`, stop and report the open findings. This step is complete when the task-depth review returns `Approval Required` within two passes.

## Test

Dispatch `pdlc-test-writer` once, scoped to this task only (its plan, its acceptance criteria, and the commit's diff), for unit coverage of the code just shipped; whole-feature acceptance coverage belongs to `pdlc-test`. It commits onto the same task branch. This step is complete when its report is in and the commit(s) it added are on the task branch and inspected.

## Land

Write the summary to a local file following [`references/implementation-summary.md`](references/implementation-summary.md), then land it:

```bash
pdlc post implement-task DELIVERY_TASK /tmp/pdlc-task-summary.md --close
```

Pass any local files implementation or validation produced, or the driver supplied, with `--attachment PATH`; see `pdlc guide attachments`.

The command records the summary as the task's `## Implementation` comment and as its PR's description, leaves the task body untouched, and closes the task. A failure posts no comment and leaves the task open, so `pdlc inspect implement` still offers it for a clean re-run; report the exact error. If the PR exists but the run failed before `prs` came back, register it with `pdlc post attach-pr DELIVERY_TASK PR_NUMBER` (idempotent), then re-run `pdlc post implement-task`. This step is complete when the JSON shows `closed: true` and this task's `taskPr`.

## Publish

Publish only when every delivery task on the record is closed. While any task is open the parent stays at `Implementation / Pending`; go straight to Report.

Write the stage evidence (the result, the task PR stack, and any exception) to a local file, or pass a short one as `text:<body>`:

```bash
pdlc post implement WORK_ITEM /tmp/pdlc-implement-evidence.md
```

The command refuses while any delivery task is open. On success every open PR in the stack is ready for review and the JSON returns the registered `pullRequest`; a failure leaves the stage unpublished, so a re-run is clean. Leave the stack unmerged; merging is a driver decision. This step is complete when the JSON shows `gateState: Review Required`.

## Report

Relay the command JSON, plus:

- the task implemented and its `taskPr`;
- the task-depth review verdict and pass count;
- the acceptance criteria verified against the running app, and their outcome;
- the unit coverage added;
- any material exception or accepted non-blocking finding;
- `## Remaining` and the current `Status`/`Gate State`.

Leave per-task files and routine green validation on the task comment. The report is complete when it contains the command output, review result, final gate, and every unresolved failure or risk.

## Requirement corrections

Surface a requirement, constraint, plan, or acceptance criterion that is factually wrong rather than working around it. Correct a mechanically provable error, such as a renamed type or a dead path, in place, updating every affected reference. Anything that changes approved intent goes to the driver: stop, report it, and name `pdlc post invalidate` against the owning stage. The approved specification stays as approved, even where the build differs.

## Boundaries

- Keep code with the `## Agent` implementer, review judgement with `pdlc-implementation-reviewer`, and unit coverage with `pdlc-test-writer`; this skill writes no code and authors no acceptance tests.
- Use the CLI as the only work-item interface; lifecycle state, evidence markers, and the parent's Product, UI, Decisions, and Open Questions sections belong to other owners.
- Branches come only from `pdlc checkout`, and PRs only from `pdlc post implement-task`; keep task work off the base branch and other tasks' branches, and leave pushing, rebasing, and merging to those tools and the driver.
- Claim only implementation, build, test, PR, or check evidence that exists.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`; those are driver actions. The stage ends at `Review Required`, never `Approved` or Testing.
- Preserve unrelated staged, unstaged, and untracked work.
