You must invoke the `acme-test-writer` skill before continuing. If it is not available, say so and exit.
You must invoke the `swift-testing` skill before continuing. If it is not available, say so and exit.

Write requirement-to-source-traceable acceptance coverage for the implemented
scope below, then run the suite and commit it on the current branch.

## Execution boundary

You are being invoked as a leaf worker for this one implemented scope.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Invoke only the test-authoring skill named above, if any; no other skill.
Write and run the coverage directly and return one report.

## Traceability map

Each row reads: requirement or acceptance criterion → expected behaviour →
source file, type, and seam → why it needs coverage.

FR-1 -> loads -> src/a.py

## In-scope source

- src/a.py
- src/shared.py
- src/b.py

## Implemented tasks

- `WORK-60-TASK-001` [CORE] First
- `WORK-60-TASK-002` [UI] Second

## Context for the commit

- Task numbers and parent work item number: `601`, `602` in `60`.
- Implementation PRs: `#40`, `#41`.

## Findings to address

Reviewer findings and failures raised against the existing coverage, verbatim.
Address every one; a finding you cannot address is reported, not dropped.

### Change request — 2026-04-01 00:00 UTC

## Findings

- detail

### Additional findings

unit-tests: assertion failed at test_a.py:12

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

## Test behaviour, not implementation

A test calls the code the way its users do and asserts the result they observe
against a literal expected value. A test that asserts which calls the code
made, or restates a constant the code contains, does neither.

Before you keep a test, ask whether it would still pass if every function it
imports returned nothing (`undefined`, `None`, `nil`). If it would, it observes
no behaviour and cannot fail for a defect. Rewrite the assertion or delete the
test.

Five shapes that still pass when the code returns nothing:

- **Weak or no assertion.** No assertion at all, or only "is defined", "is
  truthy", "does not throw", "is an instance of", or "is greater than zero".
- **Mock or absence only.** Only "was called", "was not called", "is empty",
  "is nil", or "is not this wrong value".
- **Self-referential.** The expected value comes from the code under test:
  `f(a) == f(a)`, `parsed.url == build_url(...)`.
- **Constant pin.** The assertion restates a hand-maintained constant, config
  default, table row, or prompt string: `LIMITS.max_tools == 8`.
- **Fixture asserts fixture.** The assertion reads data the test built itself,
  and the subject never runs inside the test body.

The fix: call the subject inside the test body with one concrete input and
assert the literal output or the observable effect:
`slugify("Hello, World!") == "hello-world"`. For an absence, assert the
presence on another input in the same test. For a constant, test the mechanism
that reads it with one input instead of restating the value. For a mock, assert
the payload it received or the state after the call, not that it was called.
When no such assertion exists, delete the test and report the behaviour as a
testability limitation.

Keep a test of a relation across a table's rows (a key present in two tables,
a parent that exists), and a compile-time type check.

## Report back

Return a compact report: pass/fail and commit; requirement IDs whose coverage
changed or remains uncovered; and only red tests, production defects, or
testability limitations. Do not repeat the full traceability map, file list, or
unchanged coverage boundaries — the calling skill and code host can inspect
those directly.
