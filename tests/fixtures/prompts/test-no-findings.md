No test-authoring skill is configured for this project. Follow the framework, layout, and house style of the existing test suite.

Write unit coverage for the one delivery task implemented on the current
branch, then run the suite and commit it here.

## Execution boundary

You are being invoked as a leaf worker for this one task.

Do not invoke any `pdlc-*` skill.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Invoke only the test-authoring skill named above, if any; no other skill.
Write and run the coverage directly and return one report.

## Task

`WORK-60-TASK-001` (tag included) — `[CORE] Core work`

## Scope
Build the seam.

Covers FR-1.

## Acceptance criteria
- it works

## Technical Plan

Touch one module.

## Traceability map

FR-1 -> loads -> src/a.py

## In-scope source

- src/a.py
- src/b.py

## What changed

Built the seam; criteria verified.

## Context for the commit

- Task number and parent work item number: `601` in `60`.
- Reviewer findings accepted as non-blocking, verbatim: none

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
