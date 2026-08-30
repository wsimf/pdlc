# Test-writer dispatch prompt

`pdlc-test` Step 4 fills the placeholders below and spawns `pdlc-test-writer`
once with the result. The agent knows nothing about the PDLC pipeline — give it
behaviour and files, not stage jargon.

---

```md
Write requirement-to-source-traceable acceptance coverage for the implemented
scope below, then run the suite and commit it on the current branch.

## Traceability map

<the Step 3 map, in full — one row per requirement:>

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
