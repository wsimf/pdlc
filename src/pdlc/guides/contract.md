# PDLC contract

## What this is about

PDLC is a data-driven workflow for developing one product change from intent to completion.
The work-item store is the system of record, the `pdlc` CLI is its interface, and the workflow definition supplies the valid stages, gates, transitions, and policies.

This contract tells an agent what the stored data means and which boundaries it must preserve.
It does not decide what work should happen next: `pdlc inspect` and `pdlc next` resolve the current record through the selected workflow and return `# Due Next`.

## Operating rule

Resolve before acting.

1. Use `pdlc inspect <work-item>` to resolve the record, selected workflow, current state, tasks, pull requests, evidence, and `# Due Next`.
2. Treat `Status`, `Gate State`, `Lifecycle`, task metadata, registered pull requests, and recorded evidence as machine-checked data.
3. Follow the returned `# Due Next` action and its owner; do not predict a later stage from the stage name, branch name, title, checkbox, or comment prose.
4. Use `pdlc inspect timeline <work-item>` when the evidence history matters.
5. Treat malformed state, unknown work type, missing registered data, unavailable workflow, and backend errors as blockers.

The CLI is the only supported interface to the store.
Local files are temporary inputs unless a command explicitly stores them as attachments.

## Ownership

- The parent work item owns the current product specification, decisions, open questions, phase artifacts, and durable evidence.
- The work-item state owns `Status`, `Gate State`, `Lifecycle`, `Slug`, and queue metadata.
- A delivery task owns its scope, dependencies, acceptance criteria, plan, implementation link, and task evidence.
- A delivery task is not a parent work item in its own right.
- Pull requests own code and test changes and are registered against the relevant task or parent record.
- Evidence comments explain durable events; they do not replace machine state.

## Requirement references

`FR-*`, `C-*`, and `UJ-*` identifiers support machine coverage checks.
When human-readable output cites one, quote or paraphrase the requirement beside the tag.

## Stage ownership

- Product owns the problem, goals, requirements, constraints, non-goals, success measures, assumptions, decisions, and open questions.
- UI owns the UI specification, accessibility, states, and user journeys.
- Tasks owns stable `WORK-NNN-TASK-NNN` delivery tasks, requirements, dependencies, acceptance criteria, and HITL/AFK classification.
- Technical Plan owns source ownership, architecture, sequencing, risks, and validation planning.
- Implementation owns production changes, task unit coverage, stacked pull requests, and implementation result evidence.
- Testing owns whole-feature traceability, acceptance coverage, and CI evidence across the task pull-request stack.
- Verification owns claims, runtime behavior, UX journeys, review findings, and the completion recommendation.

Each stage owner prepares only its own artifact and preserves approved upstream intent.

## Identity

Every registered record has a normalized `workType`.
Native GitHub Issue Type `Feature` resolves to `feature`, and legacy records without a type use the Feature pipeline for compatibility.
Pipeline selection happens when the record is resolved and all commands use that selected policy for routing, transitions, invalidation, churn, and completion.

The controller matches stable work-item numbers and IDs.
It never selects a record from a title, branch name, `Closes #N` text, or an in-body marker.

`Slug` is a stable machine identifier set once at creation and never rewritten.
The title remains human-readable and may change.

An unknown work type or known-but-unavailable workflow is blocked.

## Workflow data

The active workflow is data, not a universal prose sequence.
Read the selected pipeline and its `# Due Next` result when a record can follow more than one path.

The Feature pipeline is wired in `src/pdlc/domain/workflows/workflow_feature.py`.
Its ordered stages are `Product`, `UI`, `Tasks`, `Technical Plan`, `Implementation`, `Testing`, `Verification`, and terminal `Complete`.
Its completion policy requires settled stage evidence, closed delivery tasks with implementation evidence, merged registered pull requests, passing required checks, and clean Verification evidence.
Its invalidation policy records which downstream stages become stale when an upstream stage changes.
Its rework policy allows up to three delivery-rework iterations for `Implementation` and `Testing` before approval is required again.

Other workflows may define different stages, skips, completion rules, invalidation dependencies, or rework limits.
Do not apply Feature assumptions to another selected workflow.

## State

`Status` is the active stage returned by the selected workflow.
There is one active stage, not a hidden map of historical gate states.

`Gate State` describes what the active stage is waiting for:

`Pending | Review Required | Changes Required | Decision Required | CI Pending | Approval Required | Approved | Stale`

`Lifecycle` is `Planning` until `pdlc post complete` locks the record at `Completed`.

Historical phase state lives in evidence comments and artifact markers.
When an upstream artifact changes, the selected workflow determines the stale re-entry state and downstream invalidation set.

## Gates and transitions

The normal phase shape is:

`Pending / Changes Required / Stale → stage work → Review Required → independent review → Approval Required → explicit approval → workflow-selected next state`

The workflow, not the agent, determines the target state for every transition.
Commands validate the current state before mutating it and validate the resulting state after the backend responds.

`CI Pending` is a mechanical wait on the configured code host's registered pull-request checks.
When checks are pending, the state remains unchanged.
When checks pass, the workflow normally moves the current stage to `Approval Required`.
The selected rework policy may instead auto-approve `Implementation` or `Testing` and move to the next stage's `Pending`.
When checks fail, the current stage moves to `Changes Required` and the failure evidence is recorded under `PDLC-REVIEW`.

`Decision Required` means a product, architecture, UX, safety, or scope decision is needed.
It stops autonomous routing until the driver resolves or defers each recorded decision with `pdlc post decision`.
Resolution records every answer under `PDLC-RESOLUTION` and creates a separate `Product / Pending` work item for each deferred decision.

In the Feature pipeline, Product, UI, Tasks, and Technical Plan land directly at `Approval Required`.
Changing one before approval re-enters its own authoring command, resets the gate to `Stale`, and re-lands the artifact without an invalidation comment or rework count.
After publication, stage transitions require explicit approval unless the selected workflow's rework policy permits the named auto-approval exception.

Pull requests are read from the explicit registry on the parent and its delivery tasks.
Commands record them; the controller never infers them from a branch name or `Closes #N` text.

`Approved` and `Complete` are human boundaries.
Only the driver may approve, skip, invalidate, resolve decisions, or complete a record, and only in response to an explicit instruction.
Agents may request or record other workflow gates only through their owning commands.

Verification approval is consumed by the completion transition rather than by a normal next-stage approval.

## Human boundaries

- Product authoring requires an interactive driver and routes to `pdlc-write`.
- Approval is recorded by `pdlc post approve` and advances through the selected workflow.
- Skipping is pre-declared by the driver with `pdlc post skip`.
- Invalidation is a driver action through `pdlc post invalidate`.
- Decision resolution is a driver action through `pdlc post decision`.
- Completion is a driver action through `pdlc post complete`.

The loop stops on any human action, blocked state, controller error, specialist failure, or no-progress result.

## Evidence

Evidence comments are append-only unless a command's contract explicitly replaces one artifact in place.
Commands stamp markers; agents supply evidence bodies without markers.
The command resolves an evidence body from a file path or `text:<body>` and refuses unknown paths, empty content, and bodies that already begin with a `PDLC-*` marker.
Every evidence body should identify its scope, result, relevant links, actor or source, and unresolved risks.

Valid markers are:

- `PDLC-PRODUCT`
- `PDLC-UI`
- `PDLC-TASKS`
- `PDLC-PLAN`
- `PDLC-IMPLEMENTATION`
- `PDLC-TESTING`
- `PDLC-REVIEW`
- `PDLC-COMPLETE`
- `PDLC-APPROVED`
- `PDLC-AUTOAPPROVED`
- `PDLC-INVALIDATED`
- `PDLC-SKIPPED`
- `PDLC-DECISION`
- `PDLC-RESOLUTION`

`PDLC-REVIEW` carries the structured independent-review metadata block when a review verdict is being recorded.
It is also the evidence marker for CI reconciliation findings that must be surfaced when the gate is `Changes Required`.
`PDLC-DECISION` carries an open `## Decision Required` block.
`PDLC-RESOLUTION` records answered or deferred decisions.
`PDLC-AUTOAPPROVED` records a workflow-selected approval bypass within the selected rework policy.
`PDLC-INVALIDATED` records a driver return to `Stale`.

For `Changes Required` and `Stale`, `pdlc inspect` summarises under `### Open Changes` every change request the stage has not addressed since it last published; `pdlc inspect changes` prints their full text.
For `Decision Required`, it renders the newest `PDLC-DECISION` under `### Evidence`.
If there is nothing to show, it reports that evidence could not be identified and stops autonomous continuation.

A delivery task's `## Technical Plan` and `## Implementation` comments are task-local exceptions and have no `PDLC-*` marker.
Task plan evidence is replaceable during re-planning; task implementation evidence and pull-request registration follow the task command contracts.

The parent body contains human-authored content only; the backend owns how records, tasks, and pull-request links are stored.

## Artifacts and attachments

The parent body contains stable named sections for Product, UI, Decisions, Open Questions, and Verification.
A stage owner may replace only its owned sections and must preserve approved upstream intent.

Delivery-task bodies contain stable task identity, scope, requirements, dependencies, acceptance criteria, and HITL/AFK classification.
Plans and implementation evidence are posted to the task when their command contract says so.

Attachments are local agent inputs.
`pdlc post` may store them under `.pdlc/<work-item-number>/attachments/`, and inspectors may render their local paths and descriptions.
Attachment metadata and file contents are not written to the work item, project, issue, or evidence comments.

## Completion

`Complete` is terminal and locked.
Completion requires the selected workflow's completion policy to pass, including its required stage evidence, task state, pull-request state, checks, and Verification evidence.
New scope belongs in a new parent work item.

## Repeatability and failure

Commands must address explicit stable IDs, validate backend responses, and preserve retry safety.
Re-running a phase updates the same parent sections or stable task IDs instead of creating duplicates.
Re-running a pending external check is safe when the command contract says it makes no mutation.
Backend failures, missing fields, rate limits, ambiguous matches, and invalid transitions are hard failures.
Never continue by guessing, silently dropping data, or inferring a state from prose.
