# Task-level implementation review prompt

`pdlc-implement` Step 5 fills the placeholders below and spawns
`pdlc-implementation-reviewer` at `task` depth with the result — once per task,
after local validation and before the task is checkpointed onto its stacked PR.

This is a shallow, single-task review: does the change deliver the task's
acceptance criteria, and is the code sound at a basic level. It is deliberately
narrower than `trailnest-ultra-review` — no multi-specialist audit, no rendered
UX or simulator pass, no exhaustive architecture sweep, no review of any task
but this one. That depth belongs to `pdlc-review` and `pdlc-verify` later.

---

````md
You are reviewing one delivery task's implementation, read-only. Report findings
and a verdict; change nothing.

## Task

`<TASK-ID>` `<title>`

<full task body: scope, non-goals, dependencies, FR/C/UJ coverage, acceptance
criteria>

## Technical Plan

<the task's `## Technical Plan` comment, verbatim>

## Change under review

Local commit, not yet pushed:

<`git show --stat <sha>` then the full `git show <sha>` diff>

Upstream tasks it builds on: <one-line implementation summary per dependency, or
"none">

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
   - concurrency — `Sendable`, actor isolation, `@MainActor`
   - `CLAUDE.md` hard constraints and architecture rules — typed units,
     `RoutePoint` at internal boundaries, no GCD, no secondary
     `CLLocationManager`, `@Observable` over `ObservableObject`, MapLibre not
     MapKit 3D, force-unwrap rules
   - an existing test broken by inspection
4. **Not in scope:** performance profiling, rendered UX, simulator journeys,
   test authoring, CI state, files outside this diff, other tasks. Note drift
   you happen to see and recommend a wider review — do not chase it here.

## Evidence

Read the changed files in the working tree to resolve anything the diff leaves
ambiguous. Use `CLAUDE.md` for the constraint list and Cupertino MCP for
Apple-API claims. Report what you cannot verify rather than guessing.

## Report

```md
Task review complete: <TASK-ID>

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
````
