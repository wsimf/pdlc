# Upstream Patch — Spec

Status: proposal for review. No code changes yet.

## Summary

Let a stage further down the pipeline correct an already-landed upstream artifact (Product, UI, Tasks, Technical Plan) in place, without returning the record to that stage, when an independent reviewer confirms no completed stage in between is affected. If something in between is affected, the record returns to the earliest affected stage with the existing `pdlc post invalidate`.

## Problem

Today the only way to fix an upstream artifact after its stage settled is `pdlc post invalidate <stage>`. That moves the record back to that stage at `Stale`, and moving forward again re-runs every stage in between. Example: during Technical Plan the tech planner finds one FR is wrong. The FR has no UI or task-breakdown impact, but fixing it through `invalidate Product` makes UI and Tasks reconcile and get approved again for nothing.

## Goals

- Fix an upstream artifact in place and keep the pipeline where it is.
- An independent read-only reviewer decides whether that is safe; the agent that found the issue does not.
- Fall back to the existing `post invalidate` for the earliest affected stage when the change is not safe to patch.
- Reuse every existing landing command's input format and validation; add no new input format.

## Non-goals

- Selective invalidation (e.g. make UI stale but keep Tasks). The record's state is a single `(stage, gate)` pointer and moving forward re-runs every stage after the target, so "earliest affected stage" is the only meaningful answer. Per-stage evidence validity would be a model change; `InvalidationPolicy.evidence_dependencies` exists but nothing reads it at runtime today.
- Patching Implementation or Testing. They are code, not documents; rework and `post invalidate` already cover them.
- Patching from Verification. Its only re-entry targets are Implementation and Testing, and its bounce flow is unchanged.

## Flow

1. A stage owner (or its reviewer) finds an issue in an upstream artifact.
2. The owner drafts the corrected artifact in the same input form that artifact's landing command already takes.
3. The artifact's own stage reviewer reviews the draft (e.g. `pdlc-product-reviewer` for Product), exactly as for a normal re-land. This produces `--evidence`.
4. If any non-skipped stage lies between the patched stage and the active stage, or the active stage already has landed work (closed tasks), `pdlc-patch-reviewer` reads the reviewed diff and every downstream artifact and returns the earliest affected stage, or `none`. This produces `--impact`.
5. If the verdict is `none`: land with `--patch`. Otherwise: `pdlc post invalidate <stage> [--task N ...]` with the impact report as evidence, and the normal stage flow takes over.

The patch reviewer runs after the stage review so it judges the diff that will actually land.

## CLI

### Surface

`--patch` and `--impact FILE` are added to the three commands that land upstream documents. No new command: each keeps its own parsing and validation, and patch mode only changes the state handling around the landing.

| Patched stage | Command |
|---|---|
| Product | `pdlc post write --work-item N --body FILE --evidence FILE --patch [--impact FILE]` |
| UI | `pdlc post tasks --work-item N --stage UI --body FILE --evidence FILE --patch [--impact FILE]` |
| Tasks | `pdlc post tasks --work-item N --stage Tasks --manifest FILE --evidence FILE --patch [--impact FILE]` |
| Technical Plan | `pdlc post plan --work-item N --manifest FILE --evidence FILE --patch [--impact FILE]` |

`--dry-run` keeps working under `--patch` and additionally reports whether `--impact` is required and which tasks the patch touches.

### Where a patch is allowed

The patched stage must be a re-entry target of the active stage (`reentry_targets`), other than the active stage itself, and must not be skipped:

| Active stage | May patch |
|---|---|
| UI | Product |
| Tasks | Product, UI |
| Technical Plan | Product, UI, Tasks |
| Implementation | Product, UI, Tasks, Technical Plan |
| Testing | Product, UI, Tasks, Technical Plan |
| Verification, Complete | nothing |

Active gate: allowed at `Pending`, `Changes Required`, `Stale`, `Review Required`, `Approval Required`. Refused at `Decision Required` (pointer to `pdlc guide decisions`), `CI Pending`, `Approved`, and on a Complete record.

`--patch` at the command's own active stage is refused: a normal land or re-author already covers it.

### When `--impact` is required

Required when at least one non-skipped stage lies strictly between the patched stage and the active stage, or when the active stage is Implementation or Testing and has closed tasks. Otherwise it is optional: the active stage's owner reconciles its own in-progress work against the new text anyway.

The impact file must parse to a verdict line:

```
Earliest affected stage: none
```

Any value other than `none` is refused with a pointer to `pdlc post invalidate <that stage>`. The CLI does not judge impact; it requires a parseable verdict that permits the patch.

### Structural refusals

These are the guardrails the CLI can enforce itself; each is refused with a pointer to `post invalidate` for the named stage.

- **Tasks manifest:** the set of task ids must equal the landed set (no added or removed tasks), and `ui`, `covers`, and `depends` must be unchanged. Only `title` and `body` may change. A patch that would reopen a closed task (its body changes) is refused: that is Implementation impact.
- **UI:** `--no-ui` must match the landed UI applicability.
- **Technical Plan:** the manifest may only target open tasks with no implementation (`hasImplementation` false). A closed or implemented task is refused: use `post invalidate Implementation --task N`.
- **Product:** no structural check beyond the existing `post write` body validation.

### Effect

In one call, after all validation passes:

1. Lands the artifact exactly as a normal land does (same section replacement / task body updates / plan comment replacement) and posts the stage's normal evidence comment, so that stage's evidence stays current.
2. Posts one `PDLC-PATCHED` comment on the record, opening with script-owned lines, then the impact report (or `No intermediate stages.` when `--impact` was not required):

   ```
   Patched stage: Product
   Active stage: Technical Plan / Pending
   ```
3. Leaves the pointer on the active stage. If the active gate is `Review Required` or `Approval Required`, resets it to `Stale`, because the active artifact was built on the old text and must be reconciled and reviewed again. Work gates are left as is.

A refusal writes nothing.

Patches do not count towards the rework / churn limit.

## Domain changes

- `Event.PATCHED`: transition from the active stage, not the patched one. Work gates map to themselves; `Review Required` / `Approval Required` map to `Stale`; every other gate raises.
- `PATCHED` added to the lifecycle markers. It is not a settlement marker, so completion's settlement count is unaffected.
- `InvalidationPolicy.can_patch(active_stage, target_stage)`: `target_stage in reentry_targets[active_stage]` and `target_stage != active_stage`, restricted to stages that land a document. Patchable stages are declared per workflow (e.g. a `patchable_stages` tuple on the policy), so routing code never names stages.
- `intermediate_stages(patched, active, skipped)`: pure helper used to decide whether `--impact` is required.

Host I/O stays in the commands and one shared helper in `internal/invalidation.py` (`land_patch`), next to `reauthor_invalidate_stage`.

## `pdlc-patch-reviewer` sub-agent

A new read-only reviewer shipped with the other reviewers (`agent/sub-agents/{claude,codex}/pdlc-patch-reviewer.*`), dispatched the same way they are.

- **Input:** the work item number, patched stage, active stage, and the reviewed patch (the diff between the landed artifact and the draft).
- **Reads:** every landed artifact downstream of the patched stage, including the active stage's closed tasks and their PRs when the active stage is Implementation or Testing.
- **Output:** a report opening with the verdict line, then per stage a short justification citing the requirement ids, journeys, or task ids it checked:

  ```
  Earliest affected stage: Tasks
  Tasks: TASK-003 — body implements the old FR-4 threshold.

  ## UI
  Unaffected — no journey references FR-4.
  ## Tasks
  Affected — TASK-003 acceptance criteria assert the old threshold.
  ```

  When the earliest affected stage is Technical Plan or Implementation, it also names the affected task ids so the caller can pass `--task`.
- It never edits the record, the draft, or source.

The prompt lives in `src/pdlc/prompts/docs/` like the other briefs if a `pdlc prompt patch-reviewer` leaf is wanted; otherwise the owning skill dispatches it directly.

## Human boundary

A patch changes an artifact the driver already approved, without a new approval of that artifact. To keep that visible:

- `pdlc inspect` lists `PDLC-PATCHED` comments since the record's last `PDLC-APPROVED` under the next `Approval Required` Due Next, so the driver sees them before approving the active stage.
- `pdlc-completer` lists every patch in the completion evidence (patched stage, when, one-line summary).

Open question: whether a Product patch should instead require explicit driver approval (`Decision Required`) before landing. Proposal: no for v1, since the driver sees it at the next approval gate.

## Skills and guides

- New `pdlc guide patch`: when to patch vs. invalidate, the reviewer order, and the `--impact` verdict format. Stage skills link it instead of repeating it.
- `pdlc-tasks`, `pdlc-plan`, `pdlc-implement`, `pdlc-test`: one step each — "upstream artifact issue found → follow `pdlc guide patch`". No stage names beyond the skill's own.
- `pdlc-complete` / `pdlc-completer`: list patches in completion evidence.
- Command help for `post write`, `post tasks`, `post plan`: new `FLAGS` lines and a patch paragraph in `DESCRIPTION`; `_usage()` synced.

## Tests

- Domain: `Event.PATCHED` per gate; `can_patch` matrix; `intermediate_stages` with skipped stages.
- Commands (file backend): each of the three commands lands under `--patch` without moving the pointer; resets `Review Required` / `Approval Required` to `Stale`; requires `--impact` exactly when intermediate stages or closed tasks exist; refuses a non-`none` verdict; each structural refusal leaves the record untouched; `PDLC-PATCHED` comment content; completion still passes after a patch.
- `inspect`: patches since last approval render under Approval Required.

## Open questions

1. Driver approval for Product patches (see Human boundary).
2. Should a Tasks patch allow changing `covers` when the change only follows a Product patch that renamed an id? Proposal: no; that goes through `invalidate Tasks`.
3. Should the patch reviewer also be allowed to return `none` for Implementation impact when only unmerged tasks are affected, leaving the implementer to pick it up? Proposal: no for v1; name the tasks and invalidate them.
