---
name: pdlc-review
description: "Identify the PDLC record artifact that is due for independent review, dispatch that stage's specialized reviewer agent with the exact scope, and record its Changes Required, Decision Required, or Approval Required outcome. Use when asked to review a PDLC record, its UI section, tasks, plan, implementation, or testing."
argument-hint: "Parent work item number to review"
---

# Review a PDLC artifact

Record an independent verdict on the one artifact due for review. `pdlc inspect review` names the artifact and the reviewer agent that owns it, that agent reviews it with the scope you hand over, and `pdlc post review` records its verdict. This skill never reviews anything itself and never reinterprets the verdict.

Read `pdlc guide contract` when resolving lifecycle questions. Use [`references/reviewer-dispatch-prompt.md`](references/reviewer-dispatch-prompt.md) as the dispatch template.

## Resolve

Require the exact parent work-item number from the conversation. If it is missing or ambiguous, stop and ask; never infer it from a title, branch, file, PR, or history. The driver may give an explicit depth or scope ("full audit of the plan", "just review TASK-004"); carry it into Scope as an override instead of auto-detecting.

Run:

```bash
pdlc inspect review WORK_ITEM
```

`## Readiness` says whether review is due. Not ready → stop and report the reason verbatim. `## Reviewer Target` names the exact artifact and the reviewer agent that owns it.

Also read `pdlc inspect timeline WORK_ITEM`: the stage's publication evidence states what was published and what its author considered out of scope, and a prior review's findings tell you what a re-review must confirm was fixed. This step is complete when `## Readiness` reads ready and the reviewer target and any prior findings are in hand.

## Scope

Only an **Implementation** review takes a depth. Default is `pass` — every task delivered in the current publication pass, with a light consistency check elsewhere. Use `task` when the driver named a specific task or journey, and `full` when they explicitly ask for a complete audit. Every other stage's reviewer always covers the whole artifact, so pass it no depth.

Gather the evidence the reviewer will need, so it never has to guess at scope:

- **UI / Tasks** — the parent body and the task tree; no source diff needed.
- **Technical Plan** — the task bodies with their plans, plus the source files those plans claim to own.
- **Implementation** — the linked PRs, their diffs, their check state, and each task's Result. Get them from `pdlc inspect`'s `pullRequests` array and from `git log`/`git diff`.
- **Testing** — the PR carrying the test commits, the coverage map, CI results, and the requirements they claim to trace.

This step is complete when the stage's scope evidence, and the depth for an Implementation review, are in hand.

## Dispatch

Spawn the agent named in `## Reviewer Target` once, building the prompt from [`references/reviewer-dispatch-prompt.md`](references/reviewer-dispatch-prompt.md) — the parent body and item ID, the `Status`/`Gate State` as read, the exact artifact, the depth for an Implementation review, the Scope evidence, prior findings on a re-review, and the driver's follow-up verbatim.

Wait for its report. Do not review the artifact yourself in parallel, and do not soften, upgrade, or reinterpret its verdict. This step is complete when the report carries exactly one verdict: `Approval Required`, `Changes Required`, or `Decision Required`.

## Record

Write the findings body to a local file, holding only the reviewer's durable outcome: actionable findings with their evidence and recommendations, prior finding IDs with their fixed/open status on a re-review, any `## Decision Required` block, and the verdict. Do not copy unchanged scope, PR inventories, coverage boundaries, or validation history, and do not add a `PDLC-*` marker. A clean review is one line naming the artifact and commit/PR. The full reviewer report stays transient.

Pass the verdict as the outcome — `approval-required`, `changes-required`, or `decision-required`:

```bash
pdlc post review WORK_ITEM changes-required /tmp/pdlc-review-findings.md
```

A `Decision Required` verdict carries the reviewer's `## Decision Required` block into the findings body; never downgrade it to `changes-required` to keep the loop moving. Pass any local files the reviewer produced, or the driver supplied, with `--attachment PATH`; see `pdlc guide attachments`.

If recording fails, keep the reviewer's report and surface the exact failure rather than losing its outcome. This step is complete when the command succeeds; read the `gateState` and `autoApproved` it returns rather than assuming the gate from the verdict.

## Report

Relay the command's JSON output, then hand back by the returned gate:

- **`Changes Required`** — name the skill that owns reconciling it, and say the findings must be carried back verbatim.
- **`Decision Required`** — stop. Tell the driver the record is parked at `Decision Required`, point them at the `PDLC-DECISION` comment, and relay the `## Decision Required` block. Name no reconciliation owner; when the driver is ready to resolve it, run `pdlc guide decisions`.
- **`Approval Required`** — tell the driver it awaits their explicit approval before the record can advance.
- **auto-approved** (`autoApproved: true`) — report that the human step was skipped and the loop continues.
- **`CI Pending`** — report that the review passed and return control to the queue loop, which monitors the registered pull requests and continues when CI settles. This is not a human stop.

Re-run at the **same scope** after reconciliation — the same depth, for an Implementation review. If a `Changes Required` finding survives two reconciliations, stop and put it to the driver as a decision rather than looping a third time.

The report is complete when it contains the command output, the verdict, the final gate, and the requested human action.

## Boundaries

- Keep review judgement with the reviewer agent; this skill reviews nothing itself.
- Do not edit source, tests, the parent work item body, delivery tasks, or any artifact under review. Reviewing and fixing are different jobs.
- Do not build, test, render, run the app, or push.
- Use the CLI as the only work-item interface, and never write lifecycle state into any work item body.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`; those are driver actions. Never set `Approved`.
- Preserve unrelated staged, unstaged, and untracked work.
- Do not claim delegated review, build, or runtime validation that did not happen.
