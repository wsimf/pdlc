---
name: pdlc-test
description: "Own the Testing stage of a PDLC record: build a requirement-to-source traceability map from the implemented tasks, dispatch pdlc-test-writer for acceptance coverage, and publish at Review Required. Never edits production source or the record's requirements, tasks, or results."
argument-hint: "Parent work item number to test"
---

# Test a PDLC implementation

Verify acceptance coverage across the whole implemented feature — every in-scope requirement and user journey, end to end, on top of the per-task coverage each task already carries. You build the requirement-to-source traceability map, `pdlc-test-writer` writes the coverage and commits it on the current branch, so the top task PR carries the acceptance suite, and `pdlc post test` publishes the stage at `Review Required`. This skill never writes or runs tests itself.

Read `pdlc guide contract` when resolving lifecycle questions. Read `pdlc guide stacks` when a task branch, its pull request, or the stack is not where `pdlc` expects it. `pdlc prompt acceptance-test-writer` builds the test writer's brief; this skill passes it through untouched and never writes a brief of its own.

## Resolve

Require the exact parent work-item number from the conversation. If it is missing or ambiguous, stop and ask; never infer it from a title, branch, file, PR, or history.

Run:

```bash
pdlc inspect test WORK_ITEM
```

`## Readiness` resolves whether coverage is due. Not ready → stop, report the reason verbatim, and name the actual owner.

`## Testable Scope` lists every task that closed with a `## Implementation` comment, its linked PRs, and the files those PRs actually touched. Read the current source at each seam to confirm the real API — never infer a signature from requirement wording or a task title. If a task's implementation comment names behaviour that doesn't correspond to any real source change, flag it as suspect and report it rather than writing tests against a claim. Nothing implemented → stop and report that.

`## Source` names the HEAD coverage will be committed on. When it lists task PRs that HEAD does not include, check that the working tree is clean, run the `pdlc checkout` command it names, and re-run `pdlc inspect test` before mapping; never map or dispatch from a lower task's branch.

If the driver explicitly asks for ad hoc coverage on a record not due for `pdlc-test`, you may build and dispatch the map, but say plainly it sits outside the stage contract and will not satisfy the Testing gate. Do not run Publish for it: report the coverage added and leave the stage exactly as found.

This step is complete when `## Readiness` reads ready, `## Source` lists no missing task PRs, and every seam in `## Testable Scope` has been confirmed in source or flagged.

## Gate

`## Readiness` lets through only these gates:

- **`Pending`** — the first pass.
- **`Changes Required`** — a reviewer found missing or failing coverage. Read `pdlc inspect changes WORK_ITEM`; that is this pass's scope. When it lists a CI failure, or a Verification bounce for a red check, follow [`references/fix-ci.md`](references/fix-ci.md) in place of Map through Check; it ends at Publish, then Report.
- **`Stale`** — implementation changed under existing coverage; reconcile it.

This step is complete when the gate and this pass's scope are known.

## Map

Produce one traceability map, in plain terms, that the test writer can act on without reading the record:

`FR-* / C-* / acceptance criterion → expected behaviour → source file, type, and seam → why it needs coverage`

Include every in-scope `FR-*` and task acceptance criterion. Include a `C-*` constraint only when it creates an observable invariant a test can actually assert. Note coverage boundaries you already know about — anything needing a device, a fixture, a permission, or manual verification.

`pdlc-testing-reviewer` audits this map as the stage's deliverable alongside the tests, so write it to a file you can pass to Publish unchanged. This step is complete when every in-scope requirement has a map row or a stated coverage boundary.

## Dispatch

Spawn `pdlc-test-writer` once with the brief `pdlc prompt acceptance-test-writer WORK_ITEM --traceability MAP_FILE` writes. It arrives complete: the map, the in-scope source, the task, parent, and PR numbers, the stage's open change requests verbatim, and the project's test-authoring routing. The command prints only the brief's path; hand the agent that path, told plainly that the file holds its instructions and that it is to read the file and carry it out in full. Do not open, edit, summarise, or paste the brief into the dispatch. A non-zero exit writes no brief and prints what the record is waiting on: report that and dispatch nothing.

The writer commits its coverage on the current branch and never pushes; neither do you. `pdlc post test` publishes the stack, so the top task PR carries the tests; there is no separate test PR.

Wait for its report and inspect the commits it names. Do not write, edit, or run tests yourself, and do not spawn a second test author for the same scope. This step is complete when its report is in and its commits are on the current branch.

## Check

Do not take the report on trust:

- Re-read the coverage commits on the current branch and the top task PR's existing checks. Missing coverage, a failing required check, or a PR not linked to the parent work item is `Changes Required` territory — report it and stop rather than publishing a clean claim. The new commits reach the PR only when Publish runs, so its checks for them land after that.
- Confirm every in-scope requirement is either covered or recorded as an explicit coverage boundary.
- A red test left deliberately to expose a real defect is a finding for the driver, not a reason to withhold the work. Report it plainly and let them decide whether implementation must be reopened.

This step is complete when the PR, its checks, and every requirement's coverage or boundary have been re-read.

## Publish

Write the evidence file from `pdlc-test-writer`'s report, holding only the compact durable result: the result, changed coverage or uncovered requirement IDs, the PR/commit, and only defects or limitations that affect the next stage. No file inventory, repeated passing-test detail, or historical findings. Supply the body only; strip any `PDLC-*` marker line the sub-agent returned.

```
Result: acceptance coverage added; PR #153 carries 41 tests.
Coverage changes: all in-scope requirements covered except FR-9.
Exception: FR-9 needs a physical device and remains uncovered.
```

Pass the traceability map through `--traceability` unchanged:

```bash
pdlc post test WORK_ITEM /tmp/pdlc-test-evidence.md \
  --traceability /tmp/pdlc-traceability.md
```

Pass any local files testing produced, such as screenshots, or the driver supplied, with `--attachment PATH`; see `pdlc guide attachments`. The command pushes the stack before it posts, so the coverage commits reach the top task PR here and nowhere else; a push failure changes no state. No PR for the current branch is `Changes Required` territory.

If the command fails, keep the evidence and map files, report the exact error, and re-read the record before retrying. This step is complete when the command's JSON shows `gateState: Review Required` and the registered `pullRequest`.

## Report

Relay the command's JSON output, plus the result, changed coverage or uncovered requirement IDs, the PR/commit, any defects or limitations that affect the next stage, and that the stage now needs review before verification.

If the workflow stopped early, report only the exact blocking condition. The report is complete when it contains the command output, the coverage outcome, the final gate, and the requested next action.

## Boundaries

- Do not edit production source, the parent work item body, or any delivery task — never their requirements, plans, or Results.
- Do not edit fixtures, package manifests, project files, agents, or other skills.
- Do not run or author tests yourself; `pdlc-test-writer` owns both.
- Do not create or push branches, and switch only with the `pdlc checkout` `## Source` names; coverage is committed on the current branch by `pdlc-test-writer` and published by `pdlc post test`.
- Use the CLI as the only work-item interface, and never write lifecycle state into any work item body.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`; those are driver actions. Never set `Approved`, and never claim the record is done from coverage alone.
- Preserve unrelated staged, unstaged, and untracked work.
- Do not claim delegated coverage, traceability, or test-run validation unless `pdlc-test-writer` actually reported it.
