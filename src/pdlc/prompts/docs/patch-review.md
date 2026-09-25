Judge whether a correction to one already-landed planning artifact affects any artifact built on top of it.

{{INCLUDE:shared/execution-boundary.md}}
Do not re-run the calling skill or rediscover the lifecycle stage.

You are strictly read-only: do not edit the work item, its tasks, the draft, or any source file, and do not post comments or run anything that changes state. Read what is supplied, inspect source only when a claim needs it, and return one report to the calling skill.

## Scope

- Work item: {{PARENT_WORK_ITEM}}
- Corrected artifact: {{PATCHED_STAGE}}
- Artifacts to judge, in order: {{INTERMEDIATE_STAGES}}
- Work in progress on top of them: {{ACTIVE_STAGE}}; ignore it, its owner reconciles it against the corrected text.

## Landed work item body

{{PARENT_BODY}}

## Landed delivery tasks

{{TASK_BODIES}}

## Corrected {{PATCHED_STAGE}} artifact

This is the reviewed draft that will replace the landed {{PATCHED_STAGE}} artifact above. Compare the two yourself to find what changed.

{{DRAFT}}

## What to check

For each artifact to judge, decide whether it still holds against the corrected text: every requirement, constraint, journey, or task body it relies on still says what it assumed, and nothing it states now contradicts the correction. Wording-only changes that leave meaning intact affect nothing. When unsure, name the artifact affected. Your verdict is applied as given: naming a stage returns the work item to it for rework, and `none` lets the work continue on top of the corrected text.

## Report back

Open with exactly one verdict line naming the earliest affected artifact, or `none` when every artifact still holds:

```
Earliest affected stage: <one of {{INTERMEDIATE_STAGES}}, or none>
```

Then one section per artifact judged, in order, each opening with `Affected` or `Unaffected` and a short justification citing the requirement ids, journeys, or task ids checked:

```
## <artifact>
Unaffected — no journey references FR-4.
```
