# Upstream Patch — Spec

Status: implemented.

## Summary

Let a later planning stage correct an already-landed upstream planning artifact (Product, UI, Tasks) in place, without returning the record to that stage, when an independent reviewer confirms no completed stage in between is affected. If something in between is affected, the record returns to the earliest affected stage with the existing `pdlc post invalidate`.

## Problem

Today the only way to fix an upstream artifact after its stage settled is `pdlc post invalidate <stage>`. That moves the record back to that stage at `Stale`, and moving forward again re-runs every stage in between. Example: during Technical Plan the tech planner finds one FR is wrong. The FR has no UI or task-breakdown impact, but fixing it through `invalidate Product` makes UI and Tasks reconcile and get approved again for nothing.

## Goals

- Fix an upstream artifact in place and keep the pipeline where it is.
- An independent read-only reviewer decides whether that is safe; the agent that found the issue does not.
- Fall back to the existing `post invalidate` for the earliest affected stage when the change is not safe to patch.
- Reuse every existing landing command's input format and validation; add no new input format.

## Non-goals

- Selective invalidation (e.g. make UI stale but keep Tasks). The record's state is a single `(stage, gate)` pointer and moving forward re-runs every stage after the target, so "earliest affected stage" is the only meaningful answer. Per-stage evidence validity would be a model change; `InvalidationPolicy.evidence_dependencies` exists but nothing reads it at runtime today.
- Patching while the active stage is a delivery stage (Implementation, Testing, Verification). Once tasks are planned and built, impact reaches plans, PRs, and tests; `post invalidate` covers that. Revisit if real usage shows the need.
- Patching Technical Plan. It is only upstream of delivery stages, so the rule above excludes it.

## Flow

1. A planning-stage owner (or its reviewer) finds an issue in an upstream planning artifact.
2. The active stage's owner drafts the corrected artifact itself, in the same input form that artifact's landing command already takes. The planner sub-agents are not dispatched for a patch: their briefs stay gated to their own stage.
3. The artifact's own stage reviewer reviews the draft (e.g. `pdlc-product-reviewer` for Product), exactly as for a normal re-land. This produces `--evidence`.
4. If any non-skipped stage lies between the patched stage and the active stage, the internal patch reviewer (see below) compares the reviewed draft with the landed artifact, reads every intermediate artifact, and returns the earliest affected stage, or `none`. This produces `--impact`.
5. If the verdict is `none`: land with `--patch`. Otherwise the owner reports to the driver, recommending `pdlc post invalidate <stage>` with the impact report as evidence; invalidation stays a driver action, and the normal stage flow takes over from there.

The patch reviewer runs after the stage review so it judges the draft that will actually land.

## CLI

### Surface

`--patch` and `--impact FILE` are added to the two commands that land upstream planning documents. No new command: each keeps its own parsing and validation, and patch mode only changes the state handling around the landing.

| Patched stage | Command |
|---|---|
| Product | `pdlc post write --work-item N --body FILE --evidence FILE --patch [--impact FILE] [--dry-run]` |
| UI | `pdlc post tasks --work-item N --stage UI --body FILE --evidence FILE --patch [--impact FILE]` |
| Tasks | `pdlc post tasks --work-item N --stage Tasks --manifest FILE --evidence FILE --patch [--impact FILE]` |

`post tasks --dry-run` keeps working under `--patch` and additionally reports whether `--impact` is required. `post write` gains `--dry-run`, valid only with `--patch`, reporting the same; `--evidence` is not required with it, matching `post tasks`.

### Where a patch is allowed

The workflow declares which stages each active stage may patch; the patched stage must also not be skipped. For the Feature pipeline:

| Active stage | May patch |
|---|---|
| UI | Product |
| Tasks | Product, UI |
| Technical Plan | Product, UI, Tasks |
| any other stage, Complete | nothing |

Active gate: allowed at `Pending`, `Changes Required`, `Stale`, `Review Required`, `Approval Required`. Refused at `Decision Required` (pointer to `pdlc guide decisions`), `Approved`, and any other gate.

`--patch` at the command's own active stage is refused: a normal land or re-author already covers it.

### When `--impact` is required

Required when at least one non-skipped stage lies strictly between the patched stage and the active stage. Otherwise it is optional: the active stage's owner reconciles its own in-progress work against the new text anyway.

The impact file must parse to a verdict line:

```
Earliest affected stage: none
```

Any value other than `none` is refused with a pointer to `pdlc post invalidate <that stage>`. The CLI does not judge impact; it requires a parseable verdict that permits the patch.

### Structural refusals

These are the guardrails the CLI can enforce itself; each is refused with a pointer to `post invalidate` for the named stage.

- **Tasks manifest:** every entry carries an `id`, the set of task ids must equal the landed set (no added or removed tasks), and each task's `ui` must be unchanged. `covers` and `depends` are not persisted on the record (only `ui`, as the title tag), so the CLI cannot compare them; `pdlc guide patch` tells the owner to keep them, and the normal breakdown validation still checks them against the parent. Only `title` and `body` may change; `"unchanged": true` entries are allowed. A plan already landed on a patched task is left in place; the Technical Plan owner reconciles it.
- **UI:** `--no-ui` must match the landed UI applicability. When `--impact` is required, the set of `UJ-*` ids must equal the landed set.
- **Product:** when `--impact` is required, the set of `FR-*` / `C-*` ids must equal the landed set. Otherwise no structural check beyond the existing `post write` body validation.

An id-set refusal points to `post invalidate Tasks`, since the landed breakdown's coverage no longer holds.

### Effect

In one call, after all validation passes:

1. Lands the artifact exactly as a normal land does (same section replacement / task body updates) and posts the stage's normal evidence comment, so that stage's evidence stays current.
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
- `InvalidationPolicy.patch_targets`: a per-workflow mapping from active stage to the stages it may patch (for Feature, the table above). `can_patch(active_stage, target_stage)` reads it, so routing code never names stages.
- `intermediate_stages(patched, active, skipped)`: pure helper used to decide whether `--impact` is required.

Host I/O stays in the commands and one shared helper in `internal/invalidation.py` (`land_patch`), next to `reauthor_invalidate_stage`.

## Patch reviewer (internal)

The patch reviewer judges the PDLC process itself, not the work item's product or code, so PDLC owns it outright:

- **Not shipped as a sub-agent declaration.** There is no `pdlc-patch-reviewer` file under `agent/sub-agents/`, so nothing is installed into a consuming repo's agent directory and nothing there can shadow or replace it.
- **Not routable.** There is no `[agents]` / `[skills]` slot for it and `pdlc inspect capability` does not know it. Repo and machine config cannot override it.
- **Brief owned by the package.** The prompt lives in `src/pdlc/prompts/docs/patch-review.md` and is rendered by a hidden `pdlc prompt patch-reviewer WORK_ITEM --stage STAGE (--body FILE | --manifest FILE) [--file]` leaf, taking the same draft input as the patched stage's landing command. The leaf is absent from `pdlc --help` and the `pdlc prompt --help` index (like `prepare` / `cleanup`); only `pdlc guide patch` names it.
- **Dispatched to the built-in `general-purpose` agent** with that brief, handed over by path exactly as `pdlc-implement` hands over its briefs. The brief is the whole reviewer: role, read-only rule, inputs, and output format.
- **Read-only by instruction.** The brief's read-only rule is the only guard, as for every other PDLC reviewer.

Brief contents:

- **Input:** the work item number, patched stage, active stage, and the reviewed draft; the reviewer compares it with the landed artifact itself.
- **Reads:** every landed artifact strictly between the patched stage and the active stage.
- **Output:** a report opening with the verdict line, then per intermediate stage a short justification citing the requirement ids, journeys, or task ids it checked:

  ```
  Earliest affected stage: Tasks
  Tasks: TASK-003 — body implements the old FR-4 threshold.

  ## UI
  Unaffected — no journey references FR-4.
  ## Tasks
  Affected — TASK-003 acceptance criteria assert the old threshold.
  ```
- It never edits the record, the draft, or source.

## Human boundary

A patch changes an artifact the driver already approved, without a new approval of that artifact. To keep that visible:

- `pdlc inspect` lists `PDLC-PATCHED` comments since the record's last `PDLC-APPROVED` or `PDLC-AUTOAPPROVED` under `### Patches Since Last Approval` in the next `Approval Required` Due Next, so the driver sees them before approving the active stage.
- `pdlc-completer` lists every patch under the completion evidence's `Decisions` section (patched stage, when, one-line summary, comment reference), so the completion template is unchanged.

Open question: whether a Product patch should instead require explicit driver approval (`Decision Required`) before landing. Proposal: no for v1, since the driver sees it at the next approval gate.

## Skills and guides

- New `pdlc guide patch`: when to patch vs. invalidate (patch only when the corrected text follows from source or existing decisions; otherwise raise a decision per `pdlc guide decisions`), the reviewer order, and the `--impact` verdict format. It also says: after a patch, re-derive any local draft of the active stage from the landed artifacts before landing it, since a work gate is left as is and nothing else signals the change. Stage skills link it instead of repeating it.
- `pdlc-tasks`, `pdlc-plan`: one step each — "upstream artifact issue found → follow `pdlc guide patch`". No stage names beyond the skill's own.
- `pdlc-complete` / `pdlc-completer`: list patches in completion evidence.
- Command help for `post write`, `post tasks`: new `FLAGS` lines and a patch paragraph in `DESCRIPTION`; `_usage()` synced.

## Tests

- Domain: `Event.PATCHED` per gate; `can_patch` matrix, including refusal from every delivery stage; `intermediate_stages` with skipped stages.
- Commands (file backend): each of `post write`, `post tasks --stage UI`, `post tasks --stage Tasks` lands under `--patch` without moving the pointer; resets `Review Required` / `Approval Required` to `Stale`; requires `--impact` exactly when intermediate stages exist; refuses a non-`none` verdict; refuses `--patch` from a delivery stage; refuses a changed FR/C or UJ id set when `--impact` is required; `post write --dry-run` refused without `--patch`; each structural refusal leaves the record untouched; `PDLC-PATCHED` comment content; completion still passes after a patch.
- `inspect`: patches since last approval render under Approval Required.
- `prompt patch-reviewer`: golden brief fixtures; absent from `pdlc --help` and `pdlc prompt --help`; no capability slot resolves it.

## Open questions

1. Driver approval for Product patches (see Human boundary).
2. Should a Tasks patch allow changing `covers` when the change only follows a Product patch that renamed an id? Proposal: no; that goes through `invalidate Tasks`.
