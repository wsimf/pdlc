# PDLC delivery contract

PDLC stores its lifecycle state in a parent work item, its work item fields,
delivery tasks, pull requests, and evidence comments.

## Intake and orientation

- A new item requires an explicit feature idea. `pdlc-write` creates the
  parent work item, but only after its drafted product specification passes
  review, so no PDLC work item exists without one.
- Existing work requires an exact work item number. The `pdlc` skill's Orient mode
  is read-only: inspect the full parent work item, work item fields, delivery tasks,
  linked PRs, current source, relevant Git history, and dirty worktree state,
  then report and stop. It never advances a stage.
- Source and Git history are authoritative over stale work item prose. Never infer
  review, approval, completion, or task evidence from prose or checkboxes.

## Artifact ownership

| Stage | Canonical artifact |
|---|---|
| Product | Parent `Product` section through Open Questions |
| UI | Parent `UI` section, including UI applicability and `UJ-*` journeys |
| Tasks | Stable `WORK-NNN-TASK-NNN` delivery tasks |
| Technical Plan | A `## Technical Plan` comment on every incomplete delivery task |
| Implementation | One stacked PR per task (production code + that task's unit coverage) and a `## Implementation` comment on each task |
| Testing | Whole-feature acceptance coverage commits and requirement-to-source traceability evidence |
| Verification | Parent `Verification` section and `PDLC-VERIFICATION` report |

UI applicability is always explicit. `UI not required` still receives review
and human approval. Each task must cover at least one FR/C, every UI task must
cover one UJ, and each UJ must be covered by at least one UI task. These are
checked by `pdlc post tasks` against the parent record's own identifiers before
anything is written, not asserted by the agent that wrote the breakdown.

## Tasks, planning, and implementation

- Tasks contain scope, non-goals, dependencies, FR/C/UJ coverage, HITL/AFK,
  acceptance criteria, risks, and required evidence.
- Task creation is idempotent by stable ID. Reruns update the same task.
- Every incomplete task must have a `## Technical Plan` comment on its
  delivery task before implementation. It carries no PDLC marker; `pdlc-inspect`
  derives `hasPlan` from it and renders it. The human-authored task body is
  never touched by planning or implementation — a re-planned task gets a fresh
  comment and the latest one wins. The one exception is a machine-owned
  `<!-- pdlc:meta -->` block pinned above the body, where commands record the
  task's registered pull-request numbers; `pdlc-inspect` strips it on render.
- HITL tasks require recorded human approval before dispatch.
- `pdlc-implement` implements **one** task per invocation and then stops; the
  autonomous loop (or the driver) re-invokes it for the next while the parent
  sits at `Implementation / Pending`.
- Each task owns one branch, `pdlc/<slug>/task-NNN`. The `gh stack` extension
  owns the stack itself — its order, each branch's base, its rebases, and which
  members have landed. PDLC contributes two facts and no more: the branch name,
  derived from the task identity, and the stack entry point, which is the
  previous implemented task's registered pull request. `pdlc-implement` puts the
  branch on the stack with `gh stack init` or `gh stack checkout <pr> && gh stack
  add`, and `pdlc post implement-task` submits it with `gh stack sync --prune`
  and `gh stack submit`. Nothing infers a base branch, lists remote branches, or
  asks whether a predecessor's branch still exists; agents never `git push`,
  `git rebase`, or open PRs by hand.
- Implementation ships each task's production code **and its unit coverage** on
  the task branch — `pdlc-implement` dispatches `pdlc-test-writer` scoped to the
  single task after the task review passes. Whole-feature acceptance coverage is
  the Testing stage.
- A task closes once its commit is on its stacked PR, its `task`-depth
  `pdlc-implementation-reviewer` pass returned `Approval Required`, and a
  `## Implementation` comment records the outcome. The comment carries no PDLC
  marker; the human-authored task body is not rewritten; `pdlc-inspect` derives
  `hasImplementation` from it.
- A record's pull requests are the ones registered on it and on its tasks — by
  `pdlc post implement-task`, `pdlc post attach-pr`, `pdlc post implement`, or
  `pdlc post test`. Nothing is inferred from a `Closes #N` keyword or a branch
  name; gates read only the registry.
- Per-task closure does not gate on CI. The registered PRs' required checks are
  confirmed green in aggregate once every delivery task is closed, before the
  Implementation stage publishes.
- The parent remains `Implementation / Pending` until every task is complete.
- Stacked PRs are opt-in via `PDLC_STACKED_PRS` while the flow rolls out; with
  it unset, every task's commit lands on one shared implementation PR on the
  current branch and `pdlc-implement` may run the whole scope in one pass.

## Reviews, approval, and reconciliation

- An Implementation review carries a depth of `pass`, `task`, or `full`; every
  other stage's reviewer covers the whole artifact. The reviewer is read-only;
  controller records `Changes Required`, `Decision Required`, or
  `Approval Required`.
- The Implementation reviewer does not wait for CI — it judges the code while
  the task PR stack's checks are still in flight. A clean verdict lands
  `CI Pending`, not `Approval Required`; `pdlc post ci` then reconciles that gate
  against the live check rollup across every PR in the stack (all green, or no
  checks configured → `Approval Required`; any red → `Changes Required` with a
  `PDLC-IMPLEMENTATION` note). It is mechanical and the autonomous loop resolves
  it with no human step. Testing is unchanged.
- `Decision Required` is for a finding the owning skill cannot mechanically
  reconcile — one turning on a product, architecture, UX, safety, or scope call.
  It is raised by an `Implementation` or `Testing` reviewer, or by the
  `Verification` audit itself (`pdlc post verify --recommendation "Decision
  Required" --decision`). It carries a `## Decision Required` block, posts under
  `PDLC-DECISION`, sets `Gate State = Decision Required`, and stops the
  autonomous loop immediately with no reconciliation passes. The driver resolves
  it through `decision-resolver-workflow.md` — `pdlc post decision` lands a
  manifest of per-decision outcomes (answered, or deferred into its own
  `Product / Pending` work item) and moves the gate to `Changes Required`,
  routing back to the stage owner (`pdlc-implement`, `pdlc-test`, or
  `pdlc-verify`); a decision that invalidates approved upstream intent goes
  through `pdlc post invalidate` instead. Nothing else proceeds meanwhile.
- `pdlc-implement` additionally runs a `task`-depth `pdlc-implementation-reviewer`
  pass on every task before it is checkpointed onto its stacked PR — a shallow
  acceptance-criteria and code-level check, recorded in the task's
  `## Implementation` note. This does not move a gate and does not replace the
  stage-level review at `Review Required`.
- Re-run at the same scope after reconciliation. Stop for a human decision when a
  `Changes Required` finding survives two reconciliations, or immediately when a
  reviewer returns `Decision Required`.
- Human approval requires the named active stage at `Approval Required`, an
  unchanged reviewed artifact, settled upstream stages, an explicit human
  instruction in this turn (the commands carry no identity check), and a
  durable `PDLC-APPROVED` comment.
- One exception to the human instruction: on a record that has been reworked one
  to three times (any stage bounce), the script that would park it at
  `Implementation` or `Testing` `Approval Required` — the CI gate on green
  CI, `pdlc post review` on a clean Testing review — advances straight past
  the gate instead, posting a `PDLC-AUTOAPPROVED` comment and landing the record
  on the next stage's `Pending`. The reviewed artifact is still clean and
  upstream still settled; only the human step is dropped while the record
  iterates. Past three loops, and for `Verification` always, the human
  instruction is still required. A `Verification` `Changes Required` run may
  itself bounce an upstream stage back to `Stale` (`pdlc post verify
  --bounce STAGE`) with no driver step, which is what advances the loop count.
- An override must explicitly name the stage and the request to skip review.
  It cannot approve Pending or bypass unapproved upstream work. Record every
  waived finding or stale-artifact risk in parent Open Questions.

## Invalidation and verification

When an artifact changes, return its stage to `Stale`; retain downstream
artifacts and mark their evidence stale rather than deleting it:

| Changed stage | Downstream evidence to invalidate |
|---|---|
| Product | UI, Tasks, Technical Plan, Implementation |
| UI | Tasks, Technical Plan, Implementation |
| Tasks | Technical Plan, Implementation |
| Technical Plan | Implementation, Testing |
| Implementation | Testing, Verification |
| Testing | Verification |

Verification reconciles every task Result and constraint against current
source, requirement-to-test traceability, user journeys, rendered UX when
applicable, and cumulative review. Every evidence row links the exact
commit or PR checked. Findings are fixed and re-verified or explicitly deferred
in Open Questions; a clean report is never written while a finding is open.

## Completion

Complete only after every stage is approved, every task is complete, linked PRs
and checks are settled, and Verification is clean. The verified record is not
edited at completion: `pdlc post complete` validates one structured evidence
body (shipped scope, verification reference, delivery decisions, a
Resolved/Deferred disposition for every live Open Question, limitations, skipped
stages), posts it, locks the record, and blanks the settled `## Open Questions`
section to a pointer. A substantive change to any verified section bounces to its
owning stage; completed work items are locked, and new scope starts a new parent
work item.
