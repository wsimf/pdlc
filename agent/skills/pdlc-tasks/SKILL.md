---
name: pdlc-tasks
description: "Use when asked to break down a PDLC work item to UI or Core tasks, or to reconcile tasks of a reviewed breakdown."
argument-hint: "Parent work item number to prepare"
---

# Author UI and task artifacts

This skill does not author the UI section or the task breakdown itself. It reads one PDLC record's active stage, dispatches the sub-agent that owns that stage's artifact — `pdlc-ui-planner` for UI, `pdlc-task-planner` for Tasks — has it independently reviewed, and hands it to `pdlc post tasks`, which validates it, lands it, and stops the stage at `Approval Required`.

The division of labour is deliberate: sub-agents decide *what* the artifact says and whether it is good enough, and one script does everything that follows from it — nothing between those two is a judgement call.

When the UI or task artifact includes local files, pass each one to
`pdlc post tasks` as `--attachment PATH [--attachment-description TEXT]`.
Repeat `--attachment PATH` for multiple files; a description applies only to
the immediately preceding file. See [PDLC attachments](../pdlc/references/attachments.md).

Review happens before publication, on the local files, so the record never carries the churn of a breakdown reworked in place.

Read `.agents/skills/pdlc/references/parity-contract.md` before dispatching. This skill never records a review outcome and never sets a gate to `Approved`.

## Required input

Require an exact parent work item number. Check the current conversation for an unambiguous one before asking; never infer it from the branch, recent files, open PRs, or history alone.

The driver may give a specific follow-up ("revisit UJ-2's offline flow", "split TASK-004 in two"). Carry it forward verbatim to whichever sub-agent is dispatched.

---

## Step 1: Resolve the record and read its state

```bash
pdlc inspect WORK_ITEM
```

Returns the work item, raw work item body. `pdlc post tasks` resolves the item itself. No item or an ambiguous match is a hard stop; do not fall back to a title search.

**`Status` is the mode**: `UI` or `Tasks` → go to Step 2. Anything else → stop, report the actual `Status` and which skill owns it. Never author an artifact for a stage that isn't active.

## Step 2: Check the gate before authoring anything

Read `# Due Next`. Require `pdlc-tasks` as the owner; anything else stops here — report `Due Next` verbatim.

`Pending` (first pass) and `Stale` (upstream intent changed, or a landed artifact sent back — reconcile rather than rewrite from scratch) reach Step 3 directly. `Approval Required` also reaches Step 3 **only** when the driver has asked this turn to change the artifact: `pdlc post tasks` resets the stage to Stale itself on landing (gate reset only, no comment — the re-land's own evidence records the change). An `Approval Required` record with no such request is awaiting the driver's approval — report that and stop. UI and Tasks are reviewed before they publish, so they never sit at `Review Required` or `Changes Required` — seeing either means something wrote a state no path here produces; report it.

`pdlc post tasks` refuses to land from any other gate. A landed and approved artifact can only be changed via `pdlc post invalidate` (driver-only) — this skill never runs it.

## Step 3: Dispatch the owning sub-agent

`Status = UI` dispatches `pdlc-ui-planner`; `Status = Tasks` dispatches `pdlc-task-planner`. Build the prompt from the matching reference — [`references/ui-planner-prompt.md`](references/ui-planner-prompt.md) or [`references/task-planner-prompt.md`](references/task-planner-prompt.md) — filling in the parent body, `Status`/`Gate State`, the `Stale` reason, the driver's follow-up verbatim, and the existing task tree when there is one. This is also the agent you return to in Step 5 for reviewer findings — keep the dispatch reusable.

Only the driver skips the UI stage outright, with `pdlc post skip`; the planner itself always returns an explicit applicability statement.

## Step 4: Validate before landing anything

```bash
pdlc post tasks --work-item WORK_ITEM --stage Tasks \
  --manifest /tmp/pdlc-tasks.json --dry-run
```

Guards the stage/gate, then checks against the parent's own `FR-*`/`C-*`/`UJ-*`: every task covers at least one FR or C; every UI task covers a `UJ-*` and every `UJ-*` has a UI task; no task claims a requirement the parent doesn't declare; ids/titles unique, dependencies exist, graph acyclic; every task's `ui` is a strict `true`/`false`, never guessed. For UI: applicability is explicit (names a journey or states none required). Writes nothing.

For UI, pass `--stage UI --body /tmp/pdlc-ui.md --dry-run` instead.

Any failure prints every problem at once — send back to the sub-agent and re-run; never paper over a coverage gap by editing the manifest yourself. Clean run prints the resolved plan: assigned ids, dependency order, any dropped task.

## Step 5: Have the breakdown reviewed before it exists

Spawn `pdlc-tasks-reviewer`, building the prompt from [`references/breakdown-review-prompt.md`](references/breakdown-review-prompt.md) — the parent body, the manifest, and every task body (or the UI fragment). Read-only; returns findings and a verdict.

- **Findings** — hand to the authoring sub-agent verbatim, fix in place, re-run Step 4, re-review the same paths. Never fix the artifact yourself.
- **Clean** — those exact files are what Step 6 lands; do not regenerate or reformat.

After two failed reconciliations, stop and put the decision to the driver. The verdict is a working step, never posted to the record.

## Step 6: Land at Approval Required

```bash
pdlc post tasks --work-item WORK_ITEM --stage Tasks \
  --manifest /tmp/pdlc-tasks.json --evidence - <<'EOF'
Scope: 7 delivery tasks for offline tile pinning, split at the download-queue boundary.
Coverage: specification only; no source was changed.
Risk: TASK-004 depends on the unresolved quota decision and may need resplitting.
EOF
```

For UI, pass `--stage UI --body /tmp/pdlc-ui.md` instead. Creates/updates every artifact, posts evidence, and sets `Approval Required` in one step. When the record was at `Approval Required` (a driver change request), the same call first returns the stage to Stale itself.

Body only — the script stamps the marker and appends created/updated/retitled counts, dependency order, and anything dropped; don't hand-count those. Tasks match by stable `TASK-NNN` identity, never wording. Every task in the manifest writes on every pass, including unchanged ones. A landed task dropped from the breakdown is reported, never deleted — closing it is the driver's call.

On failure, keep the fragment/body/manifest files and report the exact failure. Once landed, delete the local UI spec or task documents — the work item store is now the record.

## Step 7: Report and hand back

The script's JSON output is the report — relay it: UI applicability/journey count, or created/updated/retitled task ids, dependency order, dropped tasks; that the reviewer's verdict was clean and after how many passes; that the stage is now at `Approval Required`. Ask for approval.

Say whether any earlier plan or result is now stale — only the driver invalidates it, with `pdlc post invalidate`. Never set `Approved` or continue into the next stage.

---

## Boundaries

- Do not edit source, tests, project files, other documentation, agents, or skills.
- Do not build, test, render, launch the simulator, or push.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete` — driver-only.
- Do not write lifecycle state into the work item body — those fields are script-owned.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim delegated authoring, review, build, or runtime validation that did not happen.

## Checklist

- [ ] Resolved with `pdlc inspect`; `Status` is `UI` or `Tasks`, gate was `Pending`, `Stale`, or `Approval Required` with a driver change request this turn
- [ ] The driver's follow-up reached the sub-agent unparaphrased
- [ ] The manifest's `covers`/`depends` match what its task bodies say
- [ ] `--dry-run` clean; any earlier coverage-gap finding went back to the sub-agent, never edited around
- [ ] `pdlc-tasks-reviewer` reviewed the actual files; verdict clean within two reconciliations
- [ ] Any reviewer finding went back to the authoring sub-agent verbatim, never fixed by hand
- [ ] The files landed are the reviewed files, not regenerated copies
- [ ] Evidence holds the comment body only — not counts the script appends itself
- [ ] Landed with exactly one `pdlc post tasks` call, leaving the stage at `Approval Required`
