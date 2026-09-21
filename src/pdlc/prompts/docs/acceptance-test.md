{{TEST_AUTHORING}}
{{#IF TEST_FRAMEWORK}}
{{TEST_FRAMEWORK}}
{{/IF}}

Write requirement-to-source-traceable acceptance coverage for the implemented
scope below, then run the suite and commit it on the current branch.

{{INCLUDE:shared/execution-boundary.md}}
Invoke only the test-authoring skill named above, if any; no other skill.
Write and run the coverage directly and return one report.

## Traceability map

Each row reads: requirement or acceptance criterion → expected behaviour →
source file, type, and seam → why it needs coverage.

{{TRACEABILITY_MAP}}

## In-scope source

{{IN_SCOPE_SOURCE}}

## Implemented tasks

{{IMPLEMENTED_TASKS}}

## Context for the commit

- Task numbers and parent work item number: {{TASK_NUMBERS}} in `{{PARENT_WORK_ITEM}}`.
- Implementation PRs: {{PULL_REQUESTS}}.
{{#IF FINDINGS}}

## Findings to address

Reviewer findings and failures raised against the existing coverage, verbatim.
Address every one; a finding you cannot address is reported, not dropped.

{{FINDINGS}}
{{/IF}}

## Rules

- This is acceptance testing: requirement → source → test traceability, not
  generic edge-case coverage.
- Never edit production source, the parent work item, or any delivery task —
  test-target files only.
- Commit on the current branch; do not create, switch, or rename a branch, and
  do not push.
- The tightest suite covering the new and related existing tests should end
  green. The one exception: a new test that correctly exposes a genuine
  production defect stays red and is reported — never weakened to pass.

{{INCLUDE:shared/test-behaviour.md}}

## Report back

Return a compact report: pass/fail and commit; requirement IDs whose coverage
changed or remains uncovered; and only red tests, production defects, or
testability limitations. Do not repeat the full traceability map, file list, or
unchanged coverage boundaries — the calling skill and code host can inspect
those directly.
