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
| Implementation | Production PRs and a `## Implementation` comment on each task |
| Testing | Test coverage commits and requirement-to-source coverage evidence |
| Verification | Parent `Verification` section and `PDLC-VERIFICATION` report |

UI applicability is always explicit. `UI not required` still receives review
and human approval. Each task must cover at least one FR/C, every UI task must
cover one UJ, and each UJ must be covered by at least one UI task. These are
checked by `pdlc-post-tasks.py` against the parent record's own identifiers before
anything is written, not asserted by the agent that wrote the breakdown.

## Tasks, planning, and implementation

- Tasks contain scope, non-goals, dependencies, FR/C/UJ coverage, HITL/AFK,
  acceptance criteria, risks, and required evidence.
- Task creation is idempotent by stable ID. Reruns update the same task.
- Every incomplete task must have a `## Technical Plan` comment on its
  delivery task before implementation. It carries no PDLC marker; `pdlc-inspect`
  derives `hasPlan` from it and renders it. The task body is never touched by
  planning or implementation — a re-planned task gets a fresh comment and the
  latest one wins.
- HITL tasks require recorded human approval before dispatch.
- A task closes once its commit is on the shared PR, its `task`-depth
  `pdlc-implementation-reviewer` pass returned `Approval Required`, and a
  `## Implementation` comment records the outcome. The comment carries no PDLC
  marker; the task body is not rewritten; `pdlc-inspect` derives
  `hasImplementation` from it.
- Per-task closure does not gate on CI. The shared PR's required checks are
  confirmed green in aggregate once every delivery task is closed, before the
  Implementation stage publishes.
- The parent remains `Implementation / Pending` until every task is complete.

## Reviews, approval, and reconciliation

- An Implementation review carries a depth of `pass`, `task`, or `full`; every
  other stage's reviewer covers the whole artifact. The reviewer is read-only;
  controller records `Changes Required`, `Decision Required`, or
  `Approval Required`.
- The Implementation reviewer does not wait for CI — it judges the code while
  the shared PR's checks are still in flight. A clean verdict lands `CI Pending`,
  not `Approval Required`; `pdlc-post-ci.py` then reconciles that gate against
  the live check rollup (green, or no checks configured → `Approval Required`;
  red → `Changes Required` with a `PDLC-IMPLEMENTATION` note). It is mechanical
  and the autonomous loop resolves it with no human step. Testing is unchanged.
- `Decision Required` is for a finding the owning skill cannot mechanically
  reconcile — one turning on a product, architecture, UX, safety, or scope call.
  It is raised by an `Implementation` or `Testing` reviewer, or by the
  `Verification` audit itself (`pdlc-post-verify.py --recommendation "Decision
  Required" --decision`). It carries a `## Decision Required` block, posts under
  `PDLC-DECISION`, sets `Gate State = Decision Required`, and stops the
  autonomous loop immediately with no reconciliation passes. The driver resolves
  it through `decision-resolver-workflow.md` — `pdlc-post-decision.py` lands a
  manifest of per-decision outcomes (answered, or deferred into its own
  `Product / Pending` work item) and moves the gate to `Changes Required`,
  routing back to the stage owner (`pdlc-implement`, `pdlc-test`, or
  `pdlc-verify`); a decision that invalidates approved upstream intent goes
  through `pdlc-post-invalidate.py` instead. Nothing else proceeds meanwhile.
- `pdlc-implement` additionally runs a `task`-depth `pdlc-implementation-reviewer`
  pass on every task before its commit is pushed — a shallow acceptance-criteria
  and code-level check, recorded in the task's `## Implementation` note. This
  does not move a gate and does not replace the stage-level review at
  `Review Required`.
- Re-run at the same scope after reconciliation. Stop for a human decision when a
  `Changes Required` finding survives two reconciliations, or immediately when a
  reviewer returns `Decision Required`.
- Human approval requires the named active stage at `Approval Required`, an
  unchanged reviewed artifact, settled upstream stages, an explicit human
  instruction in this turn (the scripts carry no identity check), and a
  durable `PDLC-APPROVED` comment.
- One exception to the human instruction: on a record that has been reworked one
  to three times (any stage bounce), the script that would park it at
  `Implementation` or `Testing` `Approval Required` — `lib/ci_gate.py` on green
  CI, `pdlc-post-review.py` on a clean Testing review — advances straight past
  the gate instead, posting a `PDLC-AUTOAPPROVED` comment and landing the record
  on the next stage's `Pending`. The reviewed artifact is still clean and
  upstream still settled; only the human step is dropped while the record
  iterates. Past three loops, and for `Verification` always, the human
  instruction is still required. A `Verification` `Changes Required` run may
  itself bounce an upstream stage back to `Stale` (`pdlc-post-verify.py
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
applicable, and cumulative ultra review. Every evidence row links the exact
commit or PR checked. Findings are fixed and re-verified or explicitly deferred
in Open Questions; a clean report is never written while a finding is open.

## Completion

Complete only after every stage is approved, every task is complete, linked PRs
and checks are settled, and Verification is clean. The verified record is not
edited at completion: `pdlc-post-complete.py` validates one structured evidence
body (shipped scope, verification reference, delivery decisions, a
Resolved/Deferred disposition for every live Open Question, limitations, skipped
stages), posts it, locks the record, and blanks the settled `## Open Questions`
section to a pointer. A substantive change to any verified section bounces to its
owning stage; completed work items are locked, and new scope starts a new parent
work item.
