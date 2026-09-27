---
name: pdlc-tasks
description: "Use when a resolved PDLC work item has UI or Tasks due, including first authoring, stale reconciliation, and an explicit driver request to re-author an unapproved artifact."
argument-hint: "Parent work item number to prepare"
---

# Prepare UI or delivery tasks

Prepare the artifact owned by the active `UI` or `Tasks` stage. The planner authors it, the reviewer checks the local files, and `pdlc post tasks` validates and lands the reviewed artifact at `Approval Required`. This skill owns orchestration; it never decides the artifact's product, UX, or technical content.

Read `pdlc guide contract` when resolving lifecycle questions. `pdlc prompt ui-planner`, `pdlc prompt task-planner`, and `pdlc prompt tasks-reviewer` build the planners' and reviewer's briefs; this skill passes each through untouched and never writes a brief of its own.

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

- `Status = UI`: dispatch `pdlc-ui-planner` with the brief `pdlc prompt ui-planner WORK_ITEM` writes. For a follow-up, supply both the current UI fragment path and the driver's verbatim follow-up; use `pdlc prompt ui-planner --help` for the paired inputs.
- `Status = Tasks`: dispatch `pdlc-task-planner` with the brief `pdlc prompt task-planner WORK_ITEM` writes. For a follow-up, supply both the current task manifest path and the driver's verbatim follow-up; use `pdlc prompt task-planner --help` for the paired inputs.

If a follow-up arrives before a local artifact exists, dispatch the first brief to obtain the planner's artifact, then rebrief that planner with the artifact path and verbatim follow-up before Validate.

For either, `--file` prints only the brief's path; hand the agent that path, told plainly that the file holds its instructions and that it is to read the file and carry it out in full. Do not open, edit, summarise, or paste the brief into the dispatch. A non-zero exit writes no brief and prints what the record is waiting on: report that and dispatch nothing.

The planner is the leaf author: it returns the UI fragment, or the revised task manifest and its task files. When a UI section or tasks already exist, the planner's brief points to generated editable copies. It does not invoke PDLC skills, edit the record, inspect source for technical design, or validate runtime behavior.

The returned artifact is complete when all required files exist, the manifest names every returned task body, and the planner reports requirement/journey coverage, dependency order, HITL/AFK classification, conflicts, and validation intentionally not run. For `UI`, the planner also reports whether UI is required; carry that verdict into Validate and Land.

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

Add `--no-ui` when the planner reported that UI is not required. The planner's applicability verdict decides the flag; never add or drop it to make a failing dry run pass.

Call `pdlc post tasks --help` for more info about that command.

The dry run must be clean before review; it writes nothing. Send every failure back to the planner verbatim and re-run; never repair a coverage or manifest claim by hand. If the error says to act differently, follow the instructions it gives instead. This step is complete when the command prints a clean resolved plan or UI applicability result.

## Review

Dispatch `pdlc-tasks-reviewer` with the brief `pdlc prompt tasks-reviewer WORK_ITEM (--manifest FILE | --fragment FILE) [--findings FILE] --file` writes — `--manifest` for a Tasks breakdown, `--fragment` for a UI section; `--findings` carries the prior pass's findings on a re-review. `--file` prints only the brief's path; hand the agent that path, told plainly that the file holds its instructions and that it is to read the file and carry it out in full. Do not open, edit, summarise, or paste the brief into the dispatch. The reviewer is read-only.

On `Changes`, send the findings verbatim to the same planner by re-running its own `prompt` brief command — `ui-planner` with the current UI fragment path, or `task-planner` with the current task manifest path — and the findings as its follow-up. Repeat Validate and Review on those same files. On `Clean`, retain those exact reviewed files for landing. After two failed reconciliation passes, stop and put the decision to the driver. The review step is complete only when the actual files have a clean reviewer verdict within two reconciliations.

## Land

Write only the evidence body to a local file; do not add a `PDLC-*` marker or script-generated counts. Then make exactly one non-dry-run call:

```bash
pdlc post tasks --work-item WORK_ITEM --stage Tasks \
  --manifest /tmp/pdlc-tasks.json --evidence /tmp/pdlc-tasks-evidence.md
```

For UI, use `--stage UI --body /tmp/pdlc-ui.md` instead of `--stage Tasks --manifest ...`, with the same `--no-ui` the dry run used. Pass any supplied local files with `--attachment PATH`; see `pdlc guide attachments`. A successful call leaves the active stage at `Approval Required`; a failed one writes nothing, so keep all local files and report the exact error. If the error says to act differently, follow the instructions it gives instead. After a successful landing, delete the temporary UI/spec/manifest/task-body files because the work-item store is now authoritative. This step is complete when the command succeeds and its output confirms the landed stage and artifact changes.

## Report

Relay the command's JSON output, plus:

- the resolved stage and why it was eligible;
- the planner's artifact paths and the review verdict/pass count;
- for UI, applicability and journey count;
- for Tasks, created/updated/retitled/removed IDs and dependency order;
- that the stage is now `Approval Required` and needs driver approval;
- whether an earlier plan or result is now stale, without invalidating it yourself.

If authoring shows a landed upstream artifact is wrong, follow `pdlc guide patch`; when the patch returns the record to an earlier stage, report that and stop. The report is complete when it contains the command output, reviewer result, final gate, requested human action, and every unresolved failure or risk.

## Boundaries

- Keep domain judgement with the planner and review judgement with `pdlc-tasks-reviewer`; do not edit their artifacts yourself.
- Use the CLI as the only work-item interface; lifecycle state and evidence markers are command-owned. Change a landed upstream artifact only through `pdlc guide patch`.
- Do not edit source, tests, project files, documentation, agents, or skills.
- Do not build, test, render, run the app, push, or claim validation that did not happen.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`; those are driver actions.
- Preserve unrelated staged, unstaged, and untracked work.
