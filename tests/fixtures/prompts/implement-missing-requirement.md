You are implementing one delivery task's production code. Commit your work on
the current branch before you report back, leaving nothing uncommitted; do not
push, branch, or open a pull request.

## Execution boundary

You are being invoked as a leaf worker for this one task.

Do not invoke any `pdlc-*` skill.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Implement the task below directly and return one report.

## Task

`WORK-60-TASK-001` (tag included) — `[CORE] Core work`

## Scope
Covers FR-9.

## Acceptance criteria
- it works

## Technical Plan

Touch one module.

## Context

- Parent work item: `60`.
- Requirements and constraints this task covers: FR-9 — not found in the record's `## Product`
- Upstream tasks it depends on, and what each shipped: none
- For a UI task: the approved `UJ-*` journey text it covers: none
  Project design-system and platform constraints are already covered by
  `AGENTS.md` / `CLAUDE.md`.

## Ownership and rules

- Leave unrelated code, staged work, and untracked files alone.
- The current branch is already correct — do not create, switch, or rename a
  branch.
- Commit on top of what is already on the branch — never amend, rebase, or squash existing commits, including your own from an earlier dispatch. Do not push; do not open or touch a pull request.
- Implement production code only. Do not create, edit, or delegate tests — coverage is owned separately.
- Stay inside the approved contract. If the plan is insufficient or wrong, stop and report rather than expanding scope.

## Report back

The commits you made, the files changed, the validation actually run, the acceptance criteria
verified against the running app and their outcome, and any point where the
plan did not fit the code.
