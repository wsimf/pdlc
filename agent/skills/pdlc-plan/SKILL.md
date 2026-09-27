---
name: pdlc-plan
description: "Use when a resolved PDLC work item has Technical Plan due, including first planning, stale or changes-required reconciliation, and an explicit driver request to re-plan an unapproved plan."
argument-hint: "Parent work item number to plan"
---

# Plan delivery tasks

Prepare the Technical Plan for every delivery task that needs one. `pdlc-tech-planner` spikes the tasks against current source and writes the plans into local task files, `pdlc-plan-reviewer` checks those files, and `pdlc post plan` validates and lands the reviewed plans at `Approval Required`. This skill owns orchestration; it never decides the plan's technical content. Review runs on the local files, before anything is landed.

Read `pdlc guide contract` when resolving lifecycle questions. `pdlc prompt tech-planner` and `pdlc prompt plan-reviewer` build the planner's and reviewer's briefs; this skill passes each through untouched and never writes a brief of its own.

## Resolve

Require the exact parent work-item number from the conversation. If it is missing or ambiguous, stop and ask; never infer it from a title, branch, file, PR, or history.

Run:

```bash
pdlc inspect WORK_ITEM
```

Read the resolved `Status`, `Gate State`, `# Due Next`, parent body, and `# Tasks` tree. Continue only when `Status` is `Technical Plan`; the Gate step below decides which gate states this skill acts on. Otherwise report the actual routing result and stop.

## Gate

Follow `# Due Next` for what to do, whatever produced that state, including a record edited outside PDLC:

- Names authoring or reauthoring (`Pending`, `Stale`): plan the tasks.
- Names the review procedure (`Review Required`): the plans were published without their local review. Go straight to Review, omitting `--manifest` so the reviewer gets the published plans as they stand, and take the manifest path from its report; on a clean verdict, Validate and Land that manifest unchanged.
- Says the work item needs changes (`Changes Required`): go to Author.
- Names user approval (`Approval Required`): re-plan only when the driver explicitly requests a plan change in this turn; landing overwrites the existing plans in place and returns to `Approval Required`. Without that request, it's a human boundary: report it and stop.
- Names a user decision (`Decision Required`): a human boundary. Report it, point the driver at `pdlc guide decisions`, and stop.

Any other due next result, a malformed record, missing evidence, unavailable workflow, or backend error is a blocker: report it and stop.

## Scope

The `# Tasks` tree marks each task `needsPlan` (open with no Technical Plan), `hasPlan`, and `hasImplementation`. This pass plans every `needsPlan` task, plus any already-planned task the evidence or the driver's follow-up sends back for reconciliation. A tree with no tasks is a blocker: report it and stop.

The planner's task files carry every open task's body and existing plan. This step is complete when the scope is known.

## Author

Dispatch `pdlc-tech-planner` once with the brief `pdlc prompt tech-planner WORK_ITEM [--follow-up FILE] --file` writes; `--follow-up` carries the driver's verbatim follow-up when there is one. The brief names a manifest of task files the planner edits in place; take its path from the planner's report. `--file` prints only the brief's path; hand the agent that path, told plainly that the file holds its instructions and that it is to read the file and carry it out in full. Do not open, edit, summarise, or paste the brief into the dispatch. A non-zero exit writes no brief and prints what the record is waiting on: report that and dispatch nothing. Keep the dispatch addressable: Review returns findings to the same planner.

The planner is the leaf author: it writes plan content into each task file and never edits a task's scope or acceptance criteria. A missing prerequisite or a decision only the driver can make stops the pass; surface it exactly rather than re-dispatching with a guessed answer.

The artifact is complete when the planner reports the manifest path, the tasks it planned or left unchanged, sequencing, dependency order, validation mapping, and any unresolved decision.

## Validate

Run:

```bash
pdlc post plan --work-item WORK_ITEM \
  --manifest MANIFEST --dry-run
```

Call `pdlc post plan --help` for the checks it runs. It writes nothing to the record. Send every failed validation back to the planner verbatim through a fresh `pdlc prompt tech-planner WORK_ITEM --current-plan-manifest-path MANIFEST --follow-up FILE --file` brief and re-run; never repair a plan or task file yourself. A warning that the record is at `Approval Required` needs the driver's change request from this turn before landing. This step is complete when the report reads `Verdict: Pass`.

## Review

Dispatch `pdlc-plan-reviewer` with the brief `pdlc prompt plan-reviewer WORK_ITEM --manifest MANIFEST [--findings FILE] --file` writes — the same manifest `pdlc post plan` takes; `--findings` carries the prior pass's findings on a re-review. `--file` prints only the brief's path; hand the agent that path, told plainly that the file holds its instructions and that it is to read the file and carry it out in full. Do not open, edit, summarise, or paste the brief into the dispatch. The reviewer is read-only.

On findings, send them verbatim to the same planner by re-running `pdlc prompt tech-planner WORK_ITEM --current-plan-manifest-path MANIFEST --follow-up FILE --file` with the findings as the follow-up, then repeat Validate and Review on the same manifest with the prior findings. On a clean verdict, land those files unchanged; pdlc refuses files that changed since their review. If a command reports that reviewed files changed, it has already restored them: follow its instructions and redo the review. After two failed reconciliation passes, stop and put the decision to the driver. The verdict is a working step and is never posted to the record. This step is complete only when the actual files have a clean reviewer verdict within two reconciliations.

## Land

Write only the evidence body to a local file, covering scope, architectural approach, validation, and unresolved risk; do not add a `PDLC-*` marker or the planned/already-planned task lists, which the command appends. Then make exactly one non-dry-run call:

```bash
pdlc post plan --work-item WORK_ITEM \
  --manifest MANIFEST --evidence /tmp/pdlc-plan-evidence.md
```

Pass any supplied local files with `--attachment PATH`; see `pdlc guide attachments`. A successful call leaves the stage at `Approval Required`; a failed one writes nothing, so keep all local files and report the exact error. After a successful landing, delete the temporary evidence file; the work-item store is now authoritative. This step is complete when the command succeeds and its JSON shows `gateState: Approval Required` and the planned task IDs.

## Report

Relay the command's JSON output, plus:

- the resolved gate and why it was eligible;
- the tasks planned and the tasks already planned and left alone;
- the architectural approach and sequencing/dependency order;
- the review verdict and pass count;
- unresolved decisions or risks;
- that the stage is now `Approval Required` and needs driver approval.

If planning shows a landed upstream artifact is wrong, follow `pdlc guide patch`; when the patch returns the record to an earlier stage, report that and stop. The report is complete when it contains the command output, reviewer result, final gate, requested human action, and every unresolved failure or risk.

## Boundaries

- Keep technical judgement with `pdlc-tech-planner` and review judgement with `pdlc-plan-reviewer`; do not edit their artifacts yourself.
- Use the CLI as the only work-item interface; lifecycle state, evidence markers, and the parent's Product, UI, Decisions, and Open Questions sections belong to other owners; change a landed upstream artifact only through `pdlc guide patch`.
- Planning describes the change; leave production source and tests untouched.
- Do not build, test, render, run the app, push, or claim validation that did not happen.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`; those are driver actions.
- Preserve unrelated staged, unstaged, and untracked work.
