# Task implementation dispatch prompt

`pdlc-implement` Step 4 fills the placeholders below and spawns exactly one
`swiftui-pro` (when the task's tag is `[UI]`) or `swift-pro` (otherwise) with the
result — one dispatch per task, after the skill has checked out the task's own
branch.

The agent knows nothing about the PDLC pipeline. Give it only what it needs to
write the code; never tell it to "figure out the PDLC conventions" itself. This
same dispatch is reused to hand back review findings (Step 5), so keep it
addressable.

---

```md
You are implementing one delivery task's production code. Make exactly one commit
and report back; do not push, branch, or open a pull request.

## Task

`<WORK-NNN-TASK-NNN>` (tag included) — `<title>`

<full task body: scope, non-goals, dependencies, FR/C/UJ coverage, acceptance
criteria>

## Technical Plan

<the task's `## Technical Plan` comment, verbatim — it lives in a comment,
rendered by `pdlc inspect task` after the body>

## Context

- Parent work item: `<number>`.
- Requirements and constraints this task covers: `<FR-* / C-* text, in full>`.
- Upstream tasks it depends on, and what each shipped: `<one summary per
  dependency, or "none">`.
- For a UI task: the approved `UJ-*` journey text it covers: `<journey text>`.
  TrailNest design-system constraints are already covered by `AGENTS.md` /
  `CLAUDE.md`.

## Ownership and rules

- Touch only these files and folders: `<exact ownership>`. Leave unrelated code,
  staged work, and untracked files alone.
- The current branch is already correct — do not create, switch, or rename a
  branch.
- Make exactly one commit, for this task's changes only, naming
  `<WORK-NNN-TASK-NNN>` in the message. Do not push; do not open or touch a pull
  request.
- Implement production code only. Do not create, edit, or delegate tests —
  coverage is owned separately.
- Stay inside the approved contract. If the plan is insufficient or wrong, stop
  and report rather than expanding scope.

## Report back

The files changed, the validation actually run, and any point where the plan did
not fit the code.
```
