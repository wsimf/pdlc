{{TEST_AUTHORING}}
{{#IF TEST_FRAMEWORK}}
{{TEST_FRAMEWORK}}
{{/IF}}

Write unit coverage for the one delivery task implemented on the current
branch, then run the suite and commit it here.

{{INCLUDE:shared/execution-boundary.md}}
Invoke only the test-authoring skill named above, if any; no other skill.
Write and run the coverage directly and return one report.

{{INCLUDE:shared/task.md}}

## Technical Plan

{{TECHNICAL_PLAN}}

## Traceability map

{{TRACEABILITY_MAP}}

## In-scope source

{{IN_SCOPE_SOURCE}}

## What changed

{{WHAT_CHANGED}}

## Context for the commit

- Task number and parent work item number: `{{TASK_NUMBER}}` in `{{PARENT_WORK_ITEM}}`.
- Reviewer findings accepted as non-blocking, verbatim: {{NONBLOCKING_FINDINGS}}

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

{{INCLUDE:shared/test-behaviour.md}}

{{INCLUDE:shared/code-comments.md}}

## Report back

Return a compact report: pass/fail and the commits; criteria and requirement
IDs whose coverage changed or remains uncovered; and only red tests, production
defects, or testability limitations. Do not repeat the traceability map or the
file list.
