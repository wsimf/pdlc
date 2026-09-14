# Test-writer dispatch prompt

`pdlc-test` Dispatch fills the placeholders below and spawns `pdlc-test-writer`
once with the result. The agent knows nothing about the PDLC pipeline — give it
behaviour and files, not stage jargon. Resolve the two leading lines from `pdlc
inspect capability test-authoring` and `pdlc inspect capability test-framework`
(drop the second when it prints nothing).

---

```md
<the line from `pdlc inspect capability test-authoring`>
<the line from `pdlc inspect capability test-framework`, when it is non-empty>

Write requirement-to-source-traceable acceptance coverage for the implemented
scope below, then run the suite and commit it on the current branch.

## Execution boundary

You are being invoked as a leaf worker for this one task.
Do not invoke any `pdlc-*` skill; invoke only the test-authoring skill named in the line above, if any.
Do not re-run the calling skill or rediscover the lifecycle stage.
Do not spawn, dispatch, or ask another agent to do this work.
Write and run the coverage directly and return one report to the calling `pdlc-test` skill.

## Traceability map

<the traceability map, in full — one row per requirement:>

`FR-* / C-* / acceptance criterion → expected behaviour → source file, type, and
seam → why it needs coverage`

## In-scope source

<the complete list of implemented source files under test>

## Context for the commit

- Task numbers and parent work item number: `<...>`.
- Implementation PRs: `<...>`.
- Reviewer findings from a `Changes Required` gate, verbatim: `<... or "none">`.

## Rules

- This is acceptance testing: requirement → source → test traceability, not
  generic edge-case coverage.
- Never edit production source, the parent work item, or any delivery task —
  test-target files only.
- Commit on the current branch; do not create or switch branches.
- The tightest suite covering the new and related existing tests should end
  green. The one exception: a new test that correctly exposes a genuine
  production defect stays red and is reported — never weakened to pass.

## Report back

Return a compact report: pass/fail and commit; requirement IDs whose coverage
changed or remains uncovered; and only red tests, production defects, or
testability limitations. Do not repeat the full traceability map, file list, or
unchanged coverage boundaries — the calling skill and code host can inspect
those directly.
```
