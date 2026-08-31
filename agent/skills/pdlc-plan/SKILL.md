---
name: pdlc-plan
description: "Use when asked to plan, spike, validate architecture, or prepare implementation for a PDLC record."
argument-hint: "Parent work item number to plan"
---

# Plan implementation

This skill confirms one PDLC record is due for planning, dispatches `pdlc-tech-planner`, has the returned plans independently reviewed, then hands them to `pdlc post plan` to validate, publish, and stop at `Approval Required`.

Review happens before publication, on the local task bodies — publishing rewrites every planned task in place, so a review afterwards would rewrite them all again on every finding.

When planning produces local files, pass each one to `pdlc post plan` as
`--attachment PATH [--attachment-description TEXT]`. Repeat `--attachment PATH`
for multiple files; a description applies only to the immediately preceding
file. See [PDLC attachments](../pdlc/references/attachments.md).

Read `../pdlc/references/parity-contract.md` before dispatching.

## Required input

Require an exact parent work item number. Check the current conversation for an unambiguous one before asking; never infer it from the branch, recent files, open PRs, or history alone.

The driver may give a specific follow-up ("re-spike TASK-003", "the last plan was wrong about the tile cache"). Carry it forward verbatim to the sub-agent.

---

## Step 1: Resolve the record and confirm the stage

```bash
pdlc inspect WORK_ITEM
```

Returns the work item, raw work item body, and the classified task tree Step 3 reads. `pdlc post plan` resolves the item itself. No item or an ambiguous match is a hard stop.

Read `# Due Next` rather than re-deriving whether planning is due. Require `pdlc-plan` as the owner; anything else stops here — report `Due Next` verbatim and name the actual owner. Never plan ahead of the active stage because tasks already exist.

## Step 2: Handle the gate

`Pending` (first pass) and `Stale` (upstream intent changed, or a landed plan sent back for reconciliation) reach this step directly. `Approval Required` also reaches it **only** when the driver has asked this turn to change the plan: `pdlc post plan` resets Technical Plan to Stale itself on landing (gate reset only, no comment — the re-land's own evidence records the change). An `Approval Required` record with no such request is awaiting the driver's approval — report that and stop.

Technical Plan accepts only `Pending`, `Stale`, or `Approval Required` (with a driver change request this turn) here. Any other gate is anomalous; report it. A landed and approved plan returns to `Stale` through driver-only invalidation.

## Step 3: Read the task tree

Step 1's `# Tasks` section carries the whole tree, classified: `hasPlan`, `hasImplementation` (the delivery task carries a `## Implementation` comment), `needsPlan` (open and unimplemented — this pass's scope). `pdlc post plan` enforces the same flags at land time.

A tree with no tasks at all stops the pass before any dispatch — report exactly rather than planning around it. An already-implemented task (`hasImplementation`) is simply out of scope for planning; `pdlc post plan` refuses a manifest that targets one.

Fetch the full body for every `needsPlan` task, and any task being reconciled:

```bash
pdlc inspect task DELIVERY_TASK [DELIVERY_TASK ...]
```

## Step 4: Dispatch `pdlc-tech-planner`

Spawn once, building the prompt from [`references/tech-planner-prompt.md`](references/tech-planner-prompt.md) — parent body, every `needsPlan` task's body, any existing plan text when reconciling, the driver's follow-up verbatim, and the source-ownership/architecture constraints. The template already tells the agent to return heading-free plan content plus a manifest and never to retype the task's own scope or criteria.

This is also the agent you return to in Step 6 for reviewer findings — keep the dispatch reusable. Wait for its report; relay judgments unaltered. A missing prerequisite or a decision only the driver can make stops the pass here — surface it exactly, don't resolve or re-dispatch with guessed answers.

## Step 5: Validate before landing anything

```bash
pdlc post plan --work-item WORK_ITEM \
  --manifest /tmp/pdlc-plan.json --dry-run
```

`--dry-run` guards the stage/gate, checks every plan file is non-empty, that no entry targets a closed/already-implemented/foreign task, and that no open unimplemented task is left unplanned. Writes nothing.

Any failure prints every problem at once — send them back to the sub-agent and re-run. Never repair a plan yourself; you didn't write it.

## Step 6: Have the plan reviewed before it lands

Spawn `pdlc-plan-reviewer`, building the prompt from [`references/plan-review-prompt.md`](references/plan-review-prompt.md) — parent body, every plan file, and the current body (plus any existing `## Technical Plan` comment) of each task being planned. Read-only; returns findings and a verdict.

- **Findings** — hand them verbatim to `pdlc-tech-planner`, re-run Step 5, then re-review the same paths with the prior findings.
- **Clean** — those exact files are what Step 7 lands; do not regenerate or reformat.

After two failed reconciliations, stop and put the decision to the driver. The verdict is a working step, never posted to the record.

## Step 7: Land at Approval Required

```bash
pdlc post plan --work-item WORK_ITEM \
  --manifest /tmp/pdlc-plan.json --evidence - <<'EOF'
Scope: planned 6 incomplete tasks (TASK-002..TASK-007) against current source.
Approach: geometry moves to ProfileFileService; no persistence schema change.
Validation: each task's criteria mapped to a focused test or build check.
Risk: TASK-005 depends on an unresolved tile-quota decision, recorded as open.
EOF
```

Rewrites each task by its stable `TASK-NNN` identity, posts evidence, sets `Approval Required` — one step, the only thing that moves the gate. When the record was at `Approval Required` (a driver change request), the same call first returns Technical Plan to Stale itself. Body only — the script stamps the marker and appends which tasks were planned or left alone; don't hand-count those. Use a file path in place of `-` for long evidence.

Do not touch the parent's `Product`, `UI`, `Decisions`, or `Open Questions` — earlier stages already own and approved them. On failure, keep the task body files and manifest, and report the exact failure.

## Step 8: Report and hand back

Tell the driver which tasks were planned, which already had a plan and were left alone, the architectural approach, sequencing/dependency order, unresolved decisions, that the reviewer's verdict was clean and after how many passes, and that the stage is now at `Approval Required`. Ask for approval.

Never set `Approved` or continue into Implementation. Planning that reveals approved upstream intent is wrong needs `pdlc post invalidate` and the owning stage — say so and stop.

---

## Boundaries

- Do not write production source or tests — planning describes the change, it does not make it.
- Do not build, test, render, run the app, or push.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete` — driver-only.
- Do not edit the parent's product, UI, decisions, or open-questions sections.
- Do not write lifecycle state into any work item body — those fields are script-owned.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim delegated planning, build, or runtime validation that did not happen.

## Checklist

- [ ] Resolved with `pdlc inspect`; `Status` is `Technical Plan`, gate was `Pending`, `Stale`, or `Approval Required` with a driver change request this turn
- [ ] Read the classified task tree; no already-implemented task (`hasImplementation`) is in the planning scope
- [ ] The driver's follow-up reached the sub-agent unparaphrased
- [ ] Each plan returned as heading-free content; the task's own scope and criteria were never retyped
- [ ] `--dry-run` clean; every finding went back to the sub-agent, never patched by hand
- [ ] `pdlc-plan-reviewer` reviewed the actual files; verdict clean within two reconciliations
- [ ] No unresolved blocking decision left implicit
- [ ] The plan files landed are the reviewed files, not regenerated copies
- [ ] Evidence holds the comment body only — scope, approach, validation, unresolved risk
- [ ] Landed with exactly one `pdlc post plan` call, leaving the stage at `Approval Required`
