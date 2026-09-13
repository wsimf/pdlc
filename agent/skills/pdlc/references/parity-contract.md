# PDLC workflow contract

## Purpose

PDLC moves one product change from an agreed problem to verified completion.
This document gives agents the minimum contract needed to use the `pdlc` CLI safely.
It describes observable states, stage ownership, command boundaries, and evidence expectations.
It does not describe the CLI implementation, storage format, provider API, branch strategy, or internal helpers.

## Source of truth

Use `pdlc inspect <work-item>` before acting.
It resolves the work item, selected workflow, current stage and gate, delivery tasks, registered pull requests, and `# Due Next`.

Use `pdlc next` when the controller needs to choose work from the queue.
Follow the returned action and owner exactly; do not infer the next action from a title, branch, checkbox, comment, or familiar stage sequence.

Use `pdlc inspect timeline <work-item>` when the evidence history affects the decision.
Use `pdlc inspect task <delivery-task>` when the task summary does not answer a scope, dependency, acceptance, or HITL/AFK question.

An exact work-item number is required for existing work.
An unknown work type, unavailable workflow, ambiguous match, malformed state, missing required data, or backend error is a blocker.

## Work item and stage ownership

The parent work item carries the current product intent, decisions, open questions, phase artifacts, and durable evidence.
Delivery tasks carry their own scope, requirements, dependencies, acceptance criteria, plans, implementation links, and task evidence.
Pull requests carry code and test changes and are linked to the relevant task or parent through PDLC commands.

| Stage | Agent-owned result |
|---|---|
| Product | Problem, goals, requirements, constraints, non-goals, success measures, decisions, and open questions. |
| UI | UI behavior, accessibility, states, and user journeys, or an explicit decision that UI is not required. |
| Tasks | Stable delivery tasks with requirement coverage, dependencies, acceptance criteria, and HITL/AFK classification. |
| Technical Plan | A plan for every delivery task that will be implemented. |
| Implementation | Production changes, task-level unit coverage, implementation evidence, and linked pull requests. |
| Testing | Whole-feature acceptance coverage, requirement traceability, and test evidence. |
| Verification | Current-source claims, runtime and UX checks where applicable, review findings, and completion recommendation. |

Each stage owner changes only its own artifact and preserves approved upstream intent.

## Workflow state

The active stage is the `Status` returned by the selected workflow.
The active gate is the `Gate State`:

`Pending | Review Required | Changes Required | Decision Required | CI Pending | Approval Required | Approved | Stale`

The selected workflow determines valid transitions, skipped stages, invalidation, rework limits, and completion requirements.
The Feature workflow currently runs `Product → UI → Tasks → Technical Plan → Implementation → Testing → Verification → Complete`.
Other workflow types may use different policies.

`# Due Next` is the authoritative routing result.
It names the current action, owner, reason, and any human boundary.

## Stage lifecycle

The usual shape is:

`Pending / Changes Required / Stale → stage work → Review Required → review → Approval Required → human approval → workflow-selected next state`

The workflow may produce a different valid result for a skip, decision, CI outcome, invalidation, or approved rework loop.
Agents report and follow that result instead of predicting it.

### Product and pre-publication stages

Product authoring is interactive and routes to `pdlc-write`.
In the Feature workflow, Product, UI, Tasks, and Technical Plan land at `Approval Required`.
Changing one before approval re-enters its owning authoring command and returns it to `Stale` for rework.

### Delivery tasks

Task identity is stable across reruns.
Complete one eligible delivery task per implementation pass, then let the controller select the next one.
Every task that will be implemented needs a current plan and implementation evidence.
Use the configured task and implementation commands to create or update task artifacts and pull-request links.

The parent remains in `Implementation / Pending` while delivery tasks remain incomplete.

### Review and CI

`Review Required` means the stage artifact is ready for the configured independent review.
The review records `Approval Required`, `Changes Required`, or `Decision Required`.

For a CI-gated stage, a clean implementation review may land `CI Pending` while registered pull-request checks run.
Run `pdlc post ci <work-item>` when the controller says CI has settled.

- Pending checks leave the record at `CI Pending`.
- Passing checks normally move the current stage to `Approval Required`.
- The selected rework policy may bypass that approval and move to the next stage's `Pending`.
- Failing checks move the current stage to `Changes Required` and record the failed checks as `PDLC-REVIEW` evidence.

### Decisions

`Decision Required` stops autonomous work.
The driver resolves each recorded question with `pdlc post decision`, either answering it or deferring it into separately tracked Product work.
Nothing else proceeds until the decision outcome is recorded.

### Human gates

The driver explicitly approves, skips, invalidates, resolves decisions, and completes work.
Use `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, `pdlc post decision`, and `pdlc post complete` only when the driver has authorized that exact action.
`Approved` and `Complete` are not inferred from prose, reviews, checkboxes, or agent recommendations.

## Invalidation and rework

When an approved artifact changes, the selected workflow returns that stage to `Stale` and identifies downstream evidence that must be revalidated.
Preserve the downstream artifacts until the owning workflow or command replaces or invalidates them.

Verification may return an upstream delivery stage to `Stale` when its configured rework path is used.
The selected workflow decides whether a later clean review can bypass human approval and how many iterations are allowed.

## Evidence

Evidence comments explain what happened and why, while machine state says where the record is now.
Commands add the marker; agents provide the body without a marker.

Use these marker names when reading evidence:

`PDLC-PRODUCT`, `PDLC-UI`, `PDLC-TASKS`, `PDLC-PLAN`, `PDLC-IMPLEMENTATION`, `PDLC-TESTING`, `PDLC-REVIEW`, `PDLC-COMPLETE`, `PDLC-APPROVED`, `PDLC-AUTOAPPROVED`, `PDLC-INVALIDATED`, `PDLC-SKIPPED`, `PDLC-DECISION`, and `PDLC-RESOLUTION`.

`pdlc inspect` uses the relevant evidence for `Changes Required`, `Stale`, and `Decision Required` to explain the gate.
If required evidence cannot be identified, stop and report the gap.

Task-level `Technical Plan` and `Implementation` evidence is read from the delivery task and follows its command contract.

## Verification and completion

Verification checks the implemented result against current source, requirements, acceptance coverage, relevant journeys, UX, and recorded decisions.
Every claim must identify the source or commit checked, and every finding must be fixed, re-verified, or explicitly deferred.

Complete only when the selected workflow reports readiness: required stages are settled, delivery tasks are complete, registered pull requests and checks satisfy policy, and Verification is clean.
`Complete` is terminal; new scope starts a new parent work item.

## Repeatability and blockers

Prefer rerunning the named CLI command when its contract says the operation is safe to retry.
Reruns update the same identified record or task rather than creating a duplicate.
Pending external checks may be polled again without changing state.
Treat invalid transitions, ambiguous identity, missing fields, rate limits, backend failures, and stale or contradictory evidence as blockers.
