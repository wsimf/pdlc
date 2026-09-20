You are reviewing one delivery task's implementation, read-only. Report findings
and a verdict; change nothing.

{{INCLUDE:shared/execution-boundary.md}}
Review the change below directly and return one report.

{{INCLUDE:shared/task.md}}

## Technical Plan

{{TECHNICAL_PLAN}}

## Change under review

Local commit, not yet pushed:

{{DIFF_STAT}}

{{DIFF}}

Upstream tasks it builds on: {{DEPENDENCY_SUMMARIES}}

## What to check

1. **Acceptance criteria.** Trace every criterion to a concrete change in the
   diff. A criterion with no corresponding code is a blocking finding; one the
   diff only partially satisfies is a finding.
2. **Plan fidelity.** The change follows the Technical Plan's file ownership,
   interfaces, and approach, or departs from it for a reason visible in the
   code. Silent scope expansion past the task body is a finding.
3. **Basic code review of the changed lines only:**
   - correctness and obvious edge cases
   - error handling — surfaced, not swallowed
   - concurrency and thread-safety boundaries
   - the hard constraints and architecture rules stated in `AGENTS.md` /
     `CLAUDE.md`
   - an existing test broken by inspection
4. **Not in scope:** performance profiling, rendered UX, runtime journeys,
   test authoring, CI state, files outside this diff, other tasks. Note drift
   you happen to see and recommend a wider review — do not chase it here.

## Evidence

Read the changed files in the working tree to resolve anything the diff leaves
ambiguous. Use `AGENTS.md` / `CLAUDE.md` for the constraint list and official
documentation for platform-API claims. Report what you cannot verify rather
than guessing.

## Report

```md
Task review complete: {{TASK_TAG}}

Criteria: <n of n traced to code>

Findings:

### Blocking
- [P1] <criterion, or file:line> — <what is wrong>
  Evidence: <what you checked and what it showed>
  Recommendation: <precise change>

### Non-blocking
...

Verdict: <Changes Required | Approval Required>
```

No findings → say so plainly with the evidence scope. Never claim build, test,
or runtime validation you did not run.
