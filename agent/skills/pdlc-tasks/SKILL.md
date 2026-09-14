---
name: pdlc-tasks
description: "Use when a resolved PDLC work item has UI or Tasks due, including first authoring, stale reconciliation, and an explicit driver request to re-author an unapproved artifact."
argument-hint: "Parent work item number to prepare"
---

# Prepare UI or delivery tasks

Prepare the artifact owned by the active `UI` or `Tasks` stage. The planner authors it, the reviewer checks the local files, and `pdlc post tasks` validates and lands the reviewed artifact at `Approval Required`. This skill owns orchestration; it never decides the artifact's product, UX, or technical content.

Read `pdlc guide contract` when resolving lifecycle questions. Use [`references/ui-planner-prompt.md`](references/ui-planner-prompt.md), [`references/task-planner-prompt.md`](references/task-planner-prompt.md), and [`references/breakdown-review-prompt.md`](references/breakdown-review-prompt.md) as dispatch templates.

## Resolve

Require the exact parent work-item number from the conversation. If it is missing or ambiguous, stop and ask; never infer it from a title, branch, file, PR, or history.

Run:

```bash
pdlc inspect WORK_ITEM
```

Read the resolved `Status`, `Gate State`, `# Due Next`, parent body, and existing task tree. Continue only when `Status` is `UI` or `Tasks`; the Gate step below decides which gate states this skill acts on, including `Approval Required` re-authoring by explicit driver request. Otherwise report the actual routing result and stop.
## Gate

Follow `# Due Next` for what to do, whatever produced that state, including a record edited outside PDLC:

- Names authoring or reauthoring (`Pending`, `Stale`): author the artifact.
- Names the review procedure (`Review Required`): skip straight to Review with the existing artifact; do not author or validate first.
- Says the work item needs changes (`Changes Required`): reconcile against the recorded evidence, the same as `Stale`, then continue through Author onward.
- Names user approval (`Approval Required`): re-author only when the driver explicitly requests an artifact change in this turn; Without that request, it's a human boundary: report it and stop.
- Names a user decision (`Decision Required`): a human boundary. Report it, point the driver at `pdlc guide decisions`, and stop.

Any other due next result, malformed record, missing evidence, unavailable workflow, or backend error is a blocker.

Carry the driver's follow-up verbatim. For `Stale`, reconcile against the existing artifact and the recorded stale reason; preserve settled or implemented task scope unless the owning contract permits its change. This step is complete when the valid authoring mode and exact follow-up are included in the dispatch.

## Author

Dispatch exactly one owning planner:

- `Status = UI`: dispatch `pdlc-ui-planner`. Before dispatch, fill the prompt's first line with `pdlc inspect capability ux-design`.
- `Status = Tasks`: dispatch `pdlc-task-planner`.

Build the prompt from the matching template with the complete parent body, `Status`/`Gate State`, stale reason, driver's verbatim follow-up, and existing task tree. The planner is the leaf author: it returns the UI fragment, or one task body per task plus a manifest. It does not invoke PDLC skills, edit the record, inspect source for technical design, or validate runtime behavior.

The returned artifact is complete when all required files exist, the manifest names every returned task body, and the planner reports requirement/journey coverage, dependency order, HITL/AFK classification, conflicts, and validation intentionally not run.

## Validate

For a Tasks breakdown, run:

```bash
pdlc post tasks --work-item WORK_ITEM --stage Tasks \
  --manifest /tmp/pdlc-tasks.json --dry-run
```

For a UI fragment, run:

```bash
pdlc post tasks --work-item WORK_ITEM --stage UI \
  --body /tmp/pdlc-ui.md --dry-run
```

Call `pdlc post tasks --help` for more info about that command.

The dry run must be clean before review. It checks stage/gate, parent `FR-*`/`C-*`/`UJ-*` coverage, task identity and titles, strict manifest `ui` values, dependency existence and acyclicity, and explicit UI applicability. It writes nothing. Send every failure back to the planner verbatim and re-run; never repair a coverage or manifest claim by hand. This step is complete when the command prints a clean resolved plan or UI applicability result.

## Review

Dispatch `pdlc-tasks-reviewer` with [`references/breakdown-review-prompt.md`](references/breakdown-review-prompt.md), the complete parent body, and the exact local artifact files. The reviewer is read-only and must review the actual files, not a summary.

On `Changes`, send the findings verbatim to the same planner, then repeat Validate and Review on the same paths. On `Clean`, retain those exact reviewed files for landing. After two failed reconciliation passes, stop and put the decision to the driver. The review step is complete only when the actual files have a clean reviewer verdict within two reconciliations.

## Land

Write only the evidence body to a local file; do not add a `PDLC-*` marker or script-generated counts. Then make exactly one non-dry-run call:

```bash
pdlc post tasks --work-item WORK_ITEM --stage Tasks \
  --manifest /tmp/pdlc-tasks.json --evidence /tmp/pdlc-tasks-evidence.md
```

For UI, use `--stage UI --body /tmp/pdlc-ui.md` instead of `--stage Tasks --manifest ...`. Repeat each supplied local file with `--attachment PATH [--attachment-description TEXT]`; a description applies only to the immediately preceding attachment. The command validates everything before writing, updates stable task identities, records dropped tasks without deleting them, stores evidence, and leaves the active stage at `Approval Required`. On failure, keep all local files and report the exact error. After a successful landing, delete the temporary UI/spec/manifest/task-body files because the work-item store is now authoritative. This step is complete when the command succeeds and its output confirms the landed stage and artifact changes.

## Report

Relay the command's JSON output, plus:

- the resolved stage and why it was eligible;
- the planner's artifact paths and the review verdict/pass count;
- for UI, applicability and journey count;
- for Tasks, created/updated/retitled IDs, dependency order, and dropped tasks;
- that the stage is now `Approval Required` and needs driver approval;
- whether an earlier plan or result is now stale, without invalidating it yourself.

The report is complete when it contains the command output, reviewer result, final gate, requested human action, and every unresolved failure or risk.

## Boundaries

- Keep domain judgement with the planner and review judgement with `pdlc-tasks-reviewer`; do not edit their artifacts yourself.
- Use the CLI as the only work-item interface; lifecycle state and evidence markers are command-owned.
- Do not edit source, tests, project files, documentation, agents, or skills.
- Do not build, test, render, run the app, push, or claim validation that did not happen.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`; those are driver actions.
- Preserve unrelated staged, unstaged, and untracked work.
