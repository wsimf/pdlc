You are reviewing one delivery task's implementation and its unit tests,
read-only. Report findings and a verdict; change nothing but your findings file.

## Execution boundary

You are being invoked as a leaf worker for this one review.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Review the change below directly and return one report.

## Task

`WORK-60-TASK-002` (tag included) — `[UI] Second`

## Scope
x

## Acceptance criteria
- ok

## Technical Plan

Touch one module.

## Change under review

Local commit, not yet pushed:

abc1234 impl
 1 file changed

diff --git a/x b/x

Upstream tasks it builds on: - `WORK-60-TASK-001` [CORE] Core work: Added the loader.

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
4. **Unit tests in the diff.** The tests cover the changed behaviour and the
   acceptance criteria, assert the correct behaviour rather than what the code
   happens to return, and do not only exercise mocks of the code under test.
   Missing or weak coverage is a test finding.
5. **Not in scope:** performance profiling, rendered UX, runtime journeys,
   feature-level or cross-task tests, CI state, files outside this diff, other
   tasks. Note drift you happen to see and recommend a wider review — do not
   chase it here.

## Evidence

Read the changed files in the working tree to resolve anything the diff leaves
ambiguous. Use `AGENTS.md` / `CLAUDE.md` for the constraint list and official
documentation for platform-API claims. Report what you cannot verify rather
than guessing.

## Report back

Write your review into `$CACHE_ROOT/.pdlc/cache/60/pdlc-implementation-findings.md`. It holds an outline of the report;
keep its `### ` headings as they are. It is the only file you may write.

File each finding under the agent that fixes it: production code under
`Implementation findings`, test code under `Test findings`. A test that fails
because the production code is wrong is an implementation finding; never ask
for a correct test to change to match the code.

Then reply with the verdict, exactly one of `Changes Required` or
`Approval Required`, and the findings file path. Never claim build, test, or
runtime validation you did not run.
