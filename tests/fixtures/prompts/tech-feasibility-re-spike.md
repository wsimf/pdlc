Spike the Product draft below against current source, decide whether it can be built as specified, and write its technical approach into the draft.

## Execution boundary

You are being invoked as a leaf worker for this one feasibility spike.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Bounded, read-only codebase exploration is the only delegation allowed.
Work from this brief. Write the approach into the draft below and report back to the calling agent.

## Draft

`$CACHE_ROOT/.pdlc/cache/new-route-sheet/pdlc-product-draft.md` — read the whole file. Its `## Product`, `## Decisions`, and `## Open Questions` sections have passed product review: they are what to build, and the spike checks them against the codebase.

## Findings on the previous approach

A technical review raised these against the approach this draft carried. Address each one the spike can settle; report the rest.

--- BEGIN PRIOR FINDINGS ---

- F1 [P1] FR-1 — "medium detent"
  Evidence: no detent API in src/ui/Sheet
  Recommendation: name the sheet's detent
Verdict: Needs Revision

--- END PRIOR FINDINGS ---

## Your Task

Write the draft's `### Technical approach` subsection in place: the last subsection of `## Product`, directly before `## Decisions`, replacing any approach the draft already carries. Follow this template, nesting its parts as `####` headings:

--- BEGIN TEMPLATE ---

# Technical approach

Write this as the `### Technical approach` subsection, the last subsection of the Product draft's `## Product` section, for a reader who will break the work into tasks and plan each one. It records whether the product as specified can be built on the current codebase and how, at the level of modules, boundaries, and data flow. Nest its parts one level below the subsection, as `####` headings:

```md
### Feasibility

Verdict: <Feasible | Feasible with caveats | Not feasible>

- <The evidence from current source behind the verdict, and each caveat or blocker with the requirement or constraint it affects.>

### Approach

- <How the feature fits the current codebase: the modules and ownership boundaries it touches, where new behaviour lives, and how data flows between them. Name modules, packages, and types; leave files, signatures, and edits to planning.>

### Risks & unknowns

- <Each risk or unknown, whether the spike settled it, and what changes if it goes wrong. Write `None` only when the spike found none.>

### Verification

- <How the finished feature will be shown to work: the kinds of tests, runtime or visual checks, and any measurement a quality requirement needs.>

### Migration & dependencies <!-- optional -->

- <Data or contract migrations, compatibility concerns, and external libraries, services, or APIs the approach relies on.>

### Slicing <!-- optional -->

- <Natural seams along which the work splits into independently deliverable tasks.>
```

`Feasibility`, `Approach`, `Risks & unknowns`, and `Verification` are required and must have real content. Omit an optional heading entirely when it adds nothing; never leave a placeholder. The verdict is one of the three values exactly; a `Not feasible` draft never lands. Keep the whole subsection to about a screen: deeper spike notes belong in the evidence body.

--- END TEMPLATE ---

The rest of the draft is read-only. Do not edit any other subsection or section, even to fix something the spike disproves: report it instead, so the author settles it with the driver.

## Spike

- Start from the draft's prior art and reuse, and confirm each cited path and type still exists and does what the draft says.
- Trace the flows the requirements touch: ownership boundaries, data flow, state, persistence, concurrency and isolation, error paths, and public API surfaces.
- Check every requirement and constraint is buildable on the current codebase, and that the quality bounds the requirements set are reachable.
- Use targeted Git history to recover earlier decisions on the same feature terms, types, and files.
- Find the natural seams along which the work splits into independently deliverable pieces.

## What the approach may say

- Name modules, packages, ownership boundaries, and types; describe how data flows between them. Leave files, signatures, task order, and line-level edits to planning.
- Back the verdict with evidence from current source. `Feasible with caveats` names each caveat and the requirement or constraint it affects; `Not feasible` names each blocker and the smallest product change that would remove it.
- Every requirement and constraint is covered by the approach, or named as a risk.

## Assumptions and open questions

If the draft carries an `### Assumptions` subsection, verify every entry against current source:

- **Holds:** propose the requirement or constraint wording that states it, for the author to fold in.
- **False:** report the falsified assumption, what it invalidates, and the smallest decision needed.
- **Cannot be settled from source:** report it as a decision for the driver.

Check each open question the same way: one that only an implementation detail answers may stay; one that changes a requirement or constraint is a decision for the driver.

## Boundaries

- Do not edit the work item, its tasks, or any record field or comment.
- Do not edit production source, tests, project files, agents, skills, or documentation.
- Do not implement, build, test, run the app, stage, commit, or push.
- Preserve unrelated staged, unstaged, and untracked work.
- Do not claim delegated exploration completed unless its result was actually received and incorporated.

## Report

Return to the calling agent:

1. The feasibility verdict and the evidence behind it.
2. Each blocker or caveat, and the smallest product change that removes it.
3. Every decision the driver must make, each with your recommended answer.
4. Every assumption and how it resolved, with the wording to fold in for each that holds.
5. Source/record drift found.
6. Exploration delegated and its results.
