You are implementing one delivery task's production code. Commit your work on
the current branch before you report back, leaving nothing uncommitted; do not
push, branch, or open a pull request.

## Execution boundary

You are being invoked as a leaf worker for this one task.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Implement the task below directly and return one report.

## Task

`WORK-60-TASK-001` (tag included) — `[CORE] First`

## Scope
x

## Acceptance criteria
- ok

## Technical Plan

Touch one module.

## Context

- Parent work item: `60`.
- Requirements and constraints this task covers: none
- Upstream tasks it depends on, and what each shipped: none
- For a UI task: the approved `UJ-*` journey text it covers: none
  Project design-system and platform constraints are already covered by
  `AGENTS.md` / `CLAUDE.md`.

## Findings to address

This task's code is already on the current branch. Address each finding below
with new commits on top; do not rewrite what is already there.

- PR #40: FAILURE (u40)

## Ownership and rules

- Leave unrelated code, staged work, and untracked files alone.
- The current branch is already correct — do not create, switch, or rename a
  branch.
- Commit on top of what is already on the branch — never amend, rebase, or squash existing commits, including your own from an earlier dispatch. Do not push; do not open or touch a pull request.
- Implement production code only. Do not create, edit, or delegate tests — coverage is owned separately.
- Stay inside the approved contract. If the plan is insufficient or wrong, stop and report rather than expanding scope.

## Code comments

Write a comment only where the code cannot say it itself. Clear code needs no
comment, and a rename or a smaller function beats a line of English explaining
a confusing one.

A comment never carries the work. It names no work item, delivery task,
requirement, journey, pull request, or branch, and it repeats no scope,
non-goal, or acceptance criterion from the task. A tag like
`WORK-12-TASK-003`, a reference to `FR-4`, or a line reading "added for the
auth task" sends the next reader to a record instead of the code, and goes
stale as soon as the code moves.

A comment describes the code as it stands today, never the change that
produced it. Drop "new", "now handles", "updated to", and "previously"; the
diff and the history own that story.

What earns a comment:

- A decision the code cannot show: why this approach rather than the obvious
  one, or what breaks if the order changes.
- A contract or ownership boundary: what a caller may assume, and what this
  code refuses to do.
- A constraint imposed from outside: a platform bug worked around, a call that
  must happen on a particular thread, a limit the API sets.

What does not:

- A restatement of the line below it.
- A name the code should carry instead. Rename the symbol.
- A TODO pointing at work nobody has agreed to. Report it instead.

Keep every comment you touch true. A comment that no longer matches the code
costs the reader more than no comment at all.

## Report back

The commits you made, the files changed, the validation actually run, the acceptance criteria
verified against the running app and their outcome, and any point where the
plan did not fit the code.
