Spike the Product draft below against current source, decide whether it can be built as specified, and write its technical approach into the draft.

{{INCLUDE:shared/execution-boundary.md}}
Bounded, read-only codebase exploration is the only delegation allowed.
Work from this brief. Write the approach into the draft below and report back to the calling agent.

## Draft

`{{DRAFT_PATH}}` — read the whole file. Its `## Product`, `## Decisions`, and `## Open Questions` sections have passed product review: they are what to build, and the spike checks them against the codebase.
{{#IF CURRENT_RECORD}}

## Current record

The draft revises this existing work item. Its other sections, and any delivery tasks it already has, are context for the approach.

--- BEGIN CURRENT RECORD ---

{{CURRENT_RECORD}}

--- END CURRENT RECORD ---
{{/IF}}
{{#IF PRIOR_FINDINGS}}

## Findings on the previous approach

A technical review raised these against the approach this draft carried. Address each one the spike can settle; report the rest.

--- BEGIN PRIOR FINDINGS ---

{{PRIOR_FINDINGS}}

--- END PRIOR FINDINGS ---
{{/IF}}

## Your Task

Write the draft's `### Technical approach` subsection in place: the last subsection of `## Product`, directly before `## Decisions`, replacing any approach the draft already carries. Follow this template, nesting its parts as `####` headings:

--- BEGIN TEMPLATE ---

{{APPROACH_TEMPLATE}}

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
