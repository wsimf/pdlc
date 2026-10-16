# Resolve a PDLC decision

Use this manual when a PDLC work item is at `<stage> / Decision Required` and the driver has asked you to resolve the recorded decisions. This is a human-gated workflow: collect context, ask the driver, publish every outcome in one manifest, and report the resulting state.

## Entry check

Run:

```bash
pdlc inspect <WORK_ITEM>
```

Continue only when `Gate State` is `Decision Required`. Otherwise report the actual state and stop; this manual does not apply.

## Step 1: Collect every open decision

Run:

```bash
pdlc inspect timeline <WORK_ITEM>
```

Find every `## DECISION` entry. Each `PDLC-DECISION` comment contains one `## Decision Required` block with `Question`, `Options`, `Recommendation`, `Blocks`, and `Why not mechanical`.

Read the parent body and every named task so each question is understood in context. A later `## RESOLUTION` entry settles a decision; exclude it from the open set.

Completion criterion: you have an exhaustive list of open decisions, with no resolved decision included.

## Step 2: Ask the driver

Ask one question per open decision. Use `AskUserQuestion` when available.

- Copy the reviewer's `Question` verbatim.
- Make the reviewer's `Recommendation` the first option and append `(Recommended)`.
- Include the other realistic options from the decision block.
- Add `Defer — split into its own work item` as the final option.

Preserve the driver's exact choice and rationale. A paraphrase can change the intent that the reconciling skill must apply.

Completion criterion: every open decision has exactly one driver outcome: an answer or a deferral.

## Step 3: Prepare deferred work items

For each deferred decision, write `/tmp/pdlc-deferred-<slug>.md` with this body:

```md
## Product

### 1. Problem
<the reviewer's concern in product terms>

### 2. Context
Split out of #<origin> during <stage> review. The reviewer's block:

> Question: <verbatim>
> Options: <verbatim>
> Recommendation: <verbatim>

### 3. Known bounds
<constraints, non-goals, owned files, and other bounds fixed by the origin>

## Decisions
- none yet

## Open Questions
- <the decision as a question to resolve>
```

This is an intake stub, not a finished specification. Completion criterion: every deferred decision has a readable stub at its exact manifest path.

## Step 4: Publish all outcomes once

Build one JSON manifest with one entry per open decision:

```json
[
  {
    "decision": "<reviewer's question>",
    "answer": "<driver's choice with verbatim intent>",
    "rationale": "<driver's rationale>",
    "affects": "<task or section that now carries it>"
  },
  {
    "decision": "<reviewer's question>",
    "defer": {
      "title": "<short title>",
      "slug": "<kebab-slug>",
      "body": "/tmp/pdlc-deferred-<slug>.md"
    }
  }
]
```

Publish it:

```bash
pdlc post decision <WORK_ITEM> --manifest /tmp/pdlc-decisions.json
```

The command creates or reuses one `Product / Pending` work item per deferral, links each new item back to the origin, records one `PDLC-RESOLUTION` comment containing every outcome, and moves the origin to `<stage> / Changes Required`.

Completion criterion: inspect the origin and confirm the resolution comment, resulting gate, and every deferred work-item number.

The next stage owner reconciles against the recorded decisions. Answered decisions are applied; deferred points are out of scope. Implementation and Testing return to independent review. Verification reruns its audit.

## Upstream intent changed

If an answer changes an approved requirement, constraint, journey, or task, stop the resolution workflow and request driver authorization to invalidate the owning stage, unless that authorization already exists. Execute the authorized transition through `pdlc post invalidate`. The owning skill must re-author the changed artifact and the workflow will clear the decision gate through its normal invalidation path.

## Report

Report the origin's resulting `Status`, `Gate State`, and `Lifecycle`; each decision with its answer or deferred work-item number; and every new work item created. Report a blocker when any command fails or the inspected state does not match the expected result.
