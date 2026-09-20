You must invoke the `acme-test-writer` skill before continuing. If it is not available, say so and exit.

Write unit coverage for the one delivery task implemented on the current
branch, then run the suite and commit it here.

## Execution boundary

You are being invoked as a leaf worker for this one task.

Do not invoke any `pdlc-*` skill.
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

Return a compact report: pass/fail and the commits; criteria and requirement
IDs whose coverage changed or remains uncovered; and only red tests, production
defects, or testability limitations. Do not repeat the traceability map or the
file list.
