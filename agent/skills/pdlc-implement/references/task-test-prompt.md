# Task test-writer dispatch prompt

`pdlc-implement` Test fills the placeholders below and spawns `pdlc-test-writer`
once per unit — a task's first implementation or a fix on top of it — after the
task-depth review returned `Approval Required` and before Land. The agent knows nothing about the PDLC
pipeline — give it behaviour and files, not stage jargon. Resolve the two
leading lines from `pdlc inspect capability test-authoring` and
`pdlc inspect capability test-framework` (drop the second when it prints
nothing).

This is unit coverage for one task's commits: its acceptance criteria and the
seams its diff introduced. Whole-feature acceptance coverage across the task
stack belongs to `pdlc-test` later; do not ask for it here. Build the
traceability map yourself from the task body, its `## Technical Plan`, and
`git log`/`git show` for the implementer's commits, and list every source file
those commits touched under `## In-scope source`. `## What changed` tells the
writer what this dispatch actually did, so the coverage targets it: for a first
implementation, the implementer's report-back in its own words; for a fix, each
review thread, red check, or finding it addressed and how, plus any reviewer
finding the implementer fixed on a second pass.

---

```md
<the line from `pdlc inspect capability test-authoring`>
<the line from `pdlc inspect capability test-framework`, when it is non-empty>

Write unit coverage for the one delivery task implemented on the current
branch, then run the suite and commit it here.

## Execution boundary

You are being invoked as a leaf worker for this one task.
Do not invoke any `pdlc-*` skill; invoke only the test-authoring skill named in the line above, if any.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Write and run the coverage directly and return one report.

## Task

`<WORK-NNN-TASK-NNN>` (tag included) — `<title>`

<full task body: scope, non-goals, dependencies, FR/C/UJ coverage, acceptance
criteria>

## Technical Plan

<the task's `## Technical Plan` comment, verbatim>

## Traceability map

<one row per acceptance criterion and covered requirement:>

`acceptance criterion / FR-* / C-* → expected behaviour → source file, type, and
seam → why it needs coverage`

## In-scope source

<every source file the task's commits touched, from `git show --stat`>

## What changed

<the implementer's report-back, verbatim: what it built and the criteria it
verified; and, for a fix, one entry per review thread, failing check, or
finding it addressed — what was asked, what changed, and in which commit. Each
entry needs a test that would have caught the original problem.>

## Context for the commit

- Task number and parent work item number: `<...>`.
- Reviewer findings accepted as non-blocking, verbatim: `<... or "none">`.

## Rules

- Cover this task only: its criteria and the seams in the files above. Do not
  write feature-level or cross-task coverage.
- Cover every entry under `## What changed`: a fixed review comment or check
  gets a test that fails on the behaviour the fix replaced.
- Treat the implementation as a black box: assert the correct behaviour from
  the task, plan, and domain rules, never what the code happens to return.
- Never edit production source, the parent work item, or any delivery task —
  test-target files only.
- Commit on the current branch; do not create, switch, or rename a branch, and
  do not push.
- The tightest suite covering the new and related existing tests should end
  green. The one exception: a new test that correctly exposes a genuine
  production defect stays red and is reported — never weakened to pass.

## Report back

Return a compact report: pass/fail and the commits; criteria and requirement
IDs whose coverage changed or remains uncovered; and only red tests, production
defects, or testability limitations. Do not repeat the traceability map or the
file list.
```
