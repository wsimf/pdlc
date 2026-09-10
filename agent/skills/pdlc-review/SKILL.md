---
name: pdlc-review
description: "Identify the PDLC record artifact that is due for independent review, dispatch that stage's specialized reviewer agent with the exact scope, and record its Changes Required, Decision Required, or Approval Required outcome. Use when asked to review a PDLC record, its UI section, tasks, plan, implementation, or testing."
argument-hint: "Parent work item number to review"
---

# Review a PDLC artifact

This skill does not review anything itself. It reads one PDLC record's active stage, dispatches that stage's specialized reviewer agent with the depth and scope spelled out, and records the outcome it recommends. Each reviewer agent owns its own stage's entire review procedure, is strictly read-only, never detects its own scope, and never changes work item state.

Read `../pdlc/references/parity-contract.md` before dispatching. This skill records `Changes Required` or `Approval Required`; it never sets `Approved`, which requires an explicit human instruction and belongs to the driver.

When a reviewer produces local files, or the driver supplied local files in
this prompt, pass each one to `pdlc post review` as
`--attachment PATH [--attachment-description TEXT]`. Repeat `--attachment PATH`
for multiple files; a description applies only to the immediately preceding
file. See [PDLC attachments](../pdlc/references/attachments.md).

## Required input

Require an exact parent work item number. Check the current conversation for an unambiguous one before asking; never infer it from the branch, recent files, open PRs, or history alone.

The driver may give an explicit depth or scope ("full audit of the plan", "just review TASK-004"). Carry it into Step 2 as an override instead of auto-detecting.

---

## Step 1: Resolve the record and confirm review is due

```bash
pdlc inspect review WORK_ITEM
```

`## Readiness` already resolves whether review is due. Not ready → stop, report the reason verbatim. `## Reviewer Target` already names the exact artifact and which reviewer agent owns it — in practice this is usually `Implementation` or `Testing`, since `UI`, `Tasks`, and `Technical Plan` are reviewed locally before publication by their owning skill; reaching `Review Required` here for one of those means something published without going through that step.

Also read `pdlc inspect timeline WORK_ITEM`: the stage's own publication evidence states what was published and what its author considered out of scope, and a prior review's findings tell you what a re-review must confirm was actually fixed.

## Step 2: Determine scope and gather evidence

Only an **Implementation** review takes a depth. Default is `pass` — every task delivered in the current publication pass, with a light consistency check elsewhere. Use `task` when the driver named a specific task or journey, and `full` when they explicitly ask for a complete audit. Every other stage's reviewer always covers the whole artifact, so pass it no depth.

Gather the evidence the reviewer will need, so it never has to guess at scope:

- **UI / Tasks** — the parent body and the task tree; no source diff needed.
- **Technical Plan** — the task bodies with their plans, plus the source files those plans claim to own.
- **Implementation** — the linked PRs, their diffs, their check state, and each task's Result. Get them from `pdlc inspect`'s `pullRequests` array and from `git log`/`git diff`.
- **Testing** — the PR carrying the test commits, the coverage map, CI results, and the requirements they claim to trace.

## Step 3: Dispatch the reviewer agent

Spawn the agent named in `## Reviewer Target` once, building the prompt from [`references/reviewer-dispatch-prompt.md`](references/reviewer-dispatch-prompt.md) — the parent body and item ID, the `Status`/`Gate State` as read, the exact artifact, the depth for an Implementation review, the Step 2 scope evidence, prior findings on a re-review, and the driver's follow-up verbatim.

Wait for its report. Do not review the artifact yourself in parallel, and do not soften, upgrade, or reinterpret its verdict.

## Step 4: Record the outcome

Write the findings body to a file and pass its path:

```bash
pdlc post review WORK_ITEM changes-required /tmp/pdlc-review-findings.md
```

The reviewer returns exactly one of three verdicts — pass the matching outcome:

| Reviewer verdict | Outcome argument | Resulting gate |
|---|---|---|
| Approval Required | `approval-required` | `Approval Required` |
| Changes Required | `changes-required` | `Changes Required` |
| Decision Required | `decision-required` | `Decision Required` |

`decision-required` is for a finding the owning skill cannot mechanically reconcile — it needs a product, architecture, UX, or scope call from the driver. The reviewer's report must carry a `## Decision Required` section (the question, the options, its recommendation, what it blocks, why it is not mechanical); `pdlc post review` refuses the outcome without one. It posts the report through the backend's blocker channel under a `PDLC-DECISION` marker, sets `Gate State = Decision Required`, and the autonomous loop stops on it immediately — no reconciliation passes are attempted. Do not downgrade a `Decision Required` verdict to `changes-required` to keep the loop moving.

The script posts the evidence and sets the gate in one step. It stamps `PDLC-REVIEW` plus a delimited metadata block containing the active `stage`, normalized `verdict`, and nullable `bounce` / `loop`, then places the supplied body under `## Findings`; supply body only, without a marker. Use a file path in place of `-` for long findings.

**Implementation only:** a clean `approval-required` verdict lands `CI Pending`, not `Approval Required` — the reviewer judged the code without waiting on the registered PR stack's CI. `pdlc post review` then reconciles it in the same call against the live checks (advancing to `Approval Required` if CI is already green, dropping to `Changes Required` with a `PDLC-IMPLEMENTATION` note if already red), and otherwise leaves it at `CI Pending` for `pdlc post ci` / the loop to resolve when CI finishes. Read the script's JSON `gateState` / `ci` to know which happened. Testing lands `Approval Required` straight from review — unless the record has 1–3 recorded Verification bounces in its named rework loop, in which case the script skips the human step (`gateState` like `Verification / Pending`, `autoApproved: true`, a `PDLC-AUTOAPPROVED` comment) per `../pdlc/references/parity-contract.md`.

If recording fails, keep the reviewer's report and surface the exact failure rather than losing its outcome.

## Step 5: Report and hand back

Record only the reviewer's durable outcome: actionable findings with their evidence and recommendations, prior finding IDs with their fixed/open status on a re-review, any decision block, and the verdict. Do not copy unchanged scope, PR inventories, coverage boundaries, or validation history. A clean review is one line naming the artifact and commit/PR. The full reviewer report remains transient input, not timeline content.

- **`Changes Required`** — name the skill that owns reconciling it, and say the findings must be carried back verbatim.
- **`Decision Required`** — stop. Tell the driver the record is parked at `Decision Required`, point them at the `PDLC-DECISION` comment, and relay the `## Decision Required` block. Name no reconciliation owner. When the driver is ready to resolve it, the `pdlc` skill runs `references/decision-resolver-workflow.md` (`pdlc post decision` lands a manifest of per-decision outcomes — answered or deferred into their own work item) — nothing proceeds until then.
- **`Approval Required`** — tell the driver it awaits their explicit approval before the record can advance.
- **auto-approved** (`autoApproved: true`, `gateState` already the next stage's `Pending`) — a Testing review on a record with 1–3 recorded Verification bounces in its named rework loop; report that the human step was skipped and the loop continues.
- **`CI Pending`** (Implementation, CI not yet settled) — stop. Tell the driver the implementation review passed and the record advances on its own once the registered PR stack's CI finishes: green → `Approval Required` (awaiting their approval), red → `Changes Required` (back to `pdlc-implement`). The loop handles this; `references/resolve-ci.md` covers a manual continue.

Re-run at the **same scope** after reconciliation — the same depth, for an Implementation review. If a `Changes Required` finding survives two reconciliations, stop and put it to the driver as a decision rather than looping a third time.

Never set `Approved`, and never advance the record yourself.

---

## Boundaries

- Do not edit source, tests, the parent work item body, delivery tasks, or any artifact under review. Reviewing and fixing are different jobs.
- Do not build, test, render, run the app, or push.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete` — driver-only.
- Do not write lifecycle state into any work item body — those fields are script-owned.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim delegated review, build, or runtime validation that did not happen.

## Checklist

- [ ] `## Readiness` from `pdlc inspect review` reports ready, and read the evidence timeline
- [ ] The artifact under review and its reviewer agent came from `## Reviewer Target`, not guessed
- [ ] Scope evidence was gathered and handed over explicitly, with a depth chosen for an Implementation review
- [ ] A re-review carried the prior findings so each could be confirmed fixed
- [ ] The verdict recorded is the reviewer's own, unaltered — including `Decision Required`, never downgraded to `changes-required`
- [ ] A `Decision Required` verdict carried a `## Decision Required` block and was recorded with `decision-required`, then handed to the driver with no reconciliation owner named
- [ ] Evidence holds only findings, changed prior-finding status, decision blocks, and the verdict
- [ ] A `Changes Required` finding surviving two reconciliations went to the driver instead of a third loop
