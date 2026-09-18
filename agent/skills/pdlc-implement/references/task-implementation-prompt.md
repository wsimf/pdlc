# Task implementation dispatch prompt

`pdlc-implement` Implement fills the placeholders below and spawns exactly one
implementer sub-agent with the result — the one named in the task's `## Agent`
section from `pdlc inspect task` (`general-purpose` when the project configures
no implementer).
One dispatch per task, after the skill has checked out the task's own branch.

Run `pdlc inspect capability build-run --name` first. A name fills every
`<build-run skill>` placeholder below. Nothing printed means the project has no
build-run capability: drop the `## Verify` section, the `<build-run skill>`
clause in `## Execution boundary`, and the "against the running app" wording in
the report-back — the agent validates as its own judgment and `AGENTS.md`
dictate.

The agent knows nothing about the PDLC pipeline. Give it only what it needs to
write the code; never tell it to "figure out the PDLC conventions" itself. This
same dispatch is reused to hand back review findings (Review), so keep it
addressable.

---

```md
You are implementing one delivery task's production code. Make exactly one commit
for this dispatch and report back; do not push, branch, or open a pull request.

## Execution boundary

You are being invoked as a leaf worker for this one task.
Do not invoke any `pdlc-*` skill.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Implement the task below directly and return one report.

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
  Project design-system and platform constraints are already covered by
  `AGENTS.md` / `CLAUDE.md`.

## Ownership and rules

- Leave unrelated code, staged work, and untracked files alone.
- The current branch is already correct — do not create, switch, or rename a
  branch.
- When this dispatch hands you review findings, that commit goes on top of your earlier one — never amend, rebase, or squash what is already there. Do not push; do not open or touch a pull request.
- Implement production code only. Do not create, edit, or delegate tests — coverage is owned separately.
- Stay inside the approved contract. If the plan is insufficient or wrong, stop and report rather than expanding scope.

## Verify

Before your commit, invoke the `<build-run skill>` skill to build and run the
app, then exercise this task's acceptance criteria against the running app. Fix
any failure yourself and re-verify; only commit once the criteria hold. <if build-run skill is present - 'If that skill is unavailable or says it cannot build or run, say so in your report rather than committing unverified.'>

## Report back

The files changed, the validation actually run, the acceptance criteria
verified against the running app and their outcome, and any point where the
plan did not fit the code.
```
