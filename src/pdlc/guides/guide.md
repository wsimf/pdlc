# PDLC agent guide

## Purpose

PDLC moves one product change from agreed intent to verified completion. The work-item store is the system of record, `pdlc` is its interface, and the selected workflow determines valid stages, gates, transitions, skips, invalidation, rework, and completion.

## Operating rule

Resolve before acting.

1. Run `pdlc inspect <WORK_ITEM>` before doing work. Treat its `Status`, `Gate State`, `Lifecycle`, tasks, pull requests, evidence, and `# Due Next` as authoritative.
2. Follow the returned action and owner exactly. Never infer work from a title, branch, checkbox, comment prose, or familiar stage sequence.
3. Use `pdlc inspect timeline <WORK_ITEM>` when evidence history matters and `pdlc inspect task <DELIVERY_TASK>` when a task summary is insufficient.
4. Treat unknown work types, unavailable workflows, malformed state, missing required data, and backend errors as blockers.
5. Local files are temporary inputs unless a command explicitly stores them as attachments.

## Context commands

| Need | Command |
| --- | --- |
| Understand this guide | `pdlc guide` |
| Check configuration before work | `pdlc doctor` |
| Look up a configuration setting | `pdlc guide config` |
| Troubleshoot a task PR stack | `pdlc guide stacks` |
| Correct a landed upstream artifact from a later stage | `pdlc guide patch` |
| Orient on one work item | `pdlc inspect <WORK_ITEM>` |
| Read the complete current specification | `pdlc inspect <WORK_ITEM> --full` |
| Read stage evidence history | `pdlc inspect timeline <WORK_ITEM>` |
| List the change requests a stage has not yet addressed | `pdlc inspect changes <WORK_ITEM> [--stage STAGE]` |
| Read one delivery task | `pdlc inspect task <DELIVERY_TASK>` |
| Find what is due next | `pdlc next --work-item <WORK_ITEM>` |
| Resolve a configured specialist | `pdlc inspect capability [SLOT]` |
| Understand a stage review | `pdlc inspect review <WORK_ITEM>` |
| Check implementation readiness | `pdlc inspect implement <WORK_ITEM>` |
| Check testing readiness | `pdlc inspect test <WORK_ITEM>` |
| Check verification readiness | `pdlc inspect verify <WORK_ITEM>` |
| Check completion readiness | `pdlc inspect complete <WORK_ITEM>` |

## Lifecycle

The Feature workflow is `Product → UI → Tasks → Technical Plan → Implementation → Testing → Verification → Complete`. Other work types may use different policies; read the selected workflow and follow `# Due Next`.

The active stage is `Status`. The active gate is `Gate State`, commonly one of `Pending`, `Review Required`, `Changes Required`, `Decision Required`, `CI Pending`, `Approval Required`, `Approved`, or `Stale`. `Lifecycle` remains `Planning` until completion locks the record at `Completed`.

The usual shape is `stage work → Review Required → independent review → Approval Required → explicit approval → workflow-selected next state`. Skips, decisions, invalidation, CI, and rework may produce a different valid result.

## Ownership

- Product owns the problem, goals, requirements, constraints, non-goals, decisions, and open questions.
- UI owns UI behavior, accessibility, states, and user journeys, or the explicit no-UI decision.
- Tasks owns stable delivery tasks, requirement coverage, dependencies, and acceptance criteria.
- Technical Plan owns source ownership, architecture, sequencing, risks, and validation planning.
- Implementation owns production changes, task-level coverage, pull requests, and implementation evidence.
- Testing owns whole-feature traceability, acceptance coverage, and test evidence.
- Verification owns current-source claims, runtime behavior, UX journeys, findings, and the completion recommendation.

Each stage owner changes only its own artifact and preserves approved upstream intent.

## Mutation boundaries

`pdlc inspect*`, `pdlc next`, `pdlc guide`, and `pdlc doctor` are read-only. `pdlc post *` commands mutate workflow state only when the owning skill or driver authorizes that transition.

Human actions remain explicit: Product authoring, approvals, skips, decision resolution, invalidation, and final completion. Do not run a mutating command merely because a record appears ready.

Execute a driver-authorized invalidation through `pdlc post invalidate`; that authorization persists across turns within the agreed work-item, stage, and task scope until fulfilled or revoked.

Commands stamp evidence markers. Agents provide the evidence body without a marker. A work-item body is current intent, not a history log; durable events belong in evidence comments.

## Autonomous routing

`pdlc next` orients the controller. When it returns an autonomous `pdlc-*` action, invoke that skill with the exact work-item number. When it returns a configured agent action, dispatch that agent with the exact action and work-item number; the specialist re-inspects the record and reports back.

Capability slots come from `.pdlc/config.toml` under `[agents]` and `[skills]`. Use `pdlc inspect capability` rather than hardcoding project-specific agents or skills. Unset agent slots use `general-purpose`; unset skill slots run inline using the fallback instruction.

## Safety

Never claim build, test, CI, GitHub, simulator, runtime, or UX evidence that was not produced or recorded. Keep static checks, tests, builds, external-host state, and runtime evidence separate. Preserve unrelated working-tree changes.

For command-specific arguments and exact output contracts, run `pdlc <COMMAND> --help`.
