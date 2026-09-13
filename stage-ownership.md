# Stage/Gate Ownership Matrix

The full 8 stages x 8 gates matrix for the Feature pipeline
(`src/pdlc/domain/workflow.py`), covering every `(Status, Gate State)`
combination `pdlc inspect` / `pdlc next` can report via `due_next()`.

- **Valid** — a real, persisted resting state; `Owner` is who `pdlc next`
  routes it to.
- **Heals** — not a state any pdlc command writes, but `Pipeline.heal()`
  recognizes exactly one correction for it; `pdlc next` applies the
  correction automatically before routing, and `pdlc continue WORK_ITEM`
  exposes the same correction standalone.
- **—** — structurally invalid, with no single correct fix; reported as
  `blocked`.

Enforced by the exhaustive test in `tests/test_domain.py`
(`DueNextMatrixTests`), which checks `due_next()`'s exact `action`, `owner`,
and `reason` for every cell.

| Stage | Gate | Status | Action | Owner | Can Continue Autonomously | Notes |
|---|---|---|---|---|---|---|
| Product | Pending | Valid | HUMAN_INPUT | Human | No | |
| Product | Review Required | Valid | REVIEW | Agent | Yes | independent review — corrected row; was already valid, not new this pass |
| Product | Changes Required | Valid | HUMAN_INPUT | Human | Maybe (evidence present and changes are clear; otherwise No) | |
| Product | Decision Required | Valid | HUMAN_DECISION | Human | No | corrected row; was already valid, not new this pass |
| Product | CI Pending | Heals | → Approval Required | Agent | Yes | not CI-gated; ignores outcome |
| Product | Approval Required | Valid | HUMAN_APPROVAL | Human | No | `pdlc post approve` |
| Product | Approved | Heals | → UI/Pending | Agent | Yes | |
| Product | Stale | Valid | HUMAN_INPUT | Human | Maybe (evidence present and changes are clear; otherwise No) | |
| UI | Pending | Valid | TASKS | Agent | Yes | |
| UI | Review Required | Valid | REVIEW | Agent | Yes | independent review, same as Product (previously blocked — `ReviewPolicy.independent` defaulted to `False`) |
| UI | Changes Required | Valid | TASKS | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| UI | Decision Required | Valid | HUMAN_DECISION | Human | No | previously blocked, same cause as Review Required |
| UI | CI Pending | Heals | → Approval Required | Agent | Yes | |
| UI | Approval Required | Valid | HUMAN_APPROVAL | Human | No | `pdlc post approve` |
| UI | Approved | Heals | → Tasks/Pending | Agent | Yes | |
| UI | Stale | Valid | TASKS | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Tasks | Pending | Valid | TASKS | Agent | Yes | |
| Tasks | Review Required | Valid | REVIEW | Agent | Yes | independent review, same as Product (previously blocked — `ReviewPolicy.independent` defaulted to `False`) |
| Tasks | Changes Required | Valid | TASKS | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Tasks | Decision Required | Valid | HUMAN_DECISION | Human | No | previously blocked, same cause as Review Required |
| Tasks | CI Pending | Heals | → Approval Required | Agent | Yes | |
| Tasks | Approval Required | Valid | HUMAN_APPROVAL | Human | No | `pdlc post approve` |
| Tasks | Approved | Heals | → Technical Plan/Pending | Agent | Yes | |
| Tasks | Stale | Valid | TASKS | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Technical Plan | Pending | Valid | PLAN | Agent | Yes | |
| Technical Plan | Review Required | Valid | REVIEW | Agent | Yes | independent review, same as Product (previously blocked — `ReviewPolicy.independent` defaulted to `False`) |
| Technical Plan | Changes Required | Valid | PLAN | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Technical Plan | Decision Required | Valid | HUMAN_DECISION | Human | No | previously blocked, same cause as Review Required |
| Technical Plan | CI Pending | Heals | → Approval Required | Agent | Yes | |
| Technical Plan | Approval Required | Valid | HUMAN_APPROVAL | Human | No | `pdlc post approve` |
| Technical Plan | Approved | Heals | → Implementation/Pending | Agent | Yes | |
| Technical Plan | Stale | Valid | PLAN | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Implementation | Pending | Valid | IMPLEMENT | Agent | Maybe (task HITL requirements may require approval) | |
| Implementation | Review Required | Valid | REVIEW | Agent | Yes | independent review |
| Implementation | Changes Required | Valid | IMPLEMENT | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Implementation | Decision Required | Valid | HUMAN_DECISION | Human | No | |
| Implementation | CI Pending | Valid | CI (`pdlc post ci`) | Agent | Yes | genuinely CI-gated — checked, not healed |
| Implementation | Approval Required | Valid | HUMAN_APPROVAL | Human | No | `pdlc post approve` |
| Implementation | Approved | Heals | → Testing/Pending | Agent | Yes | |
| Implementation | Stale | Valid | IMPLEMENT | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Testing | Pending | Valid | TEST | Agent | Yes | |
| Testing | Review Required | Valid | REVIEW | Agent | Yes | |
| Testing | Changes Required | Valid | TEST | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Testing | Decision Required | Valid | HUMAN_DECISION | Human | No | |
| Testing | CI Pending | Valid | CI (`pdlc post ci`) | Agent | Yes | genuinely CI-gated — checked, not healed |
| Testing | Approval Required | Valid | HUMAN_APPROVAL | Human | No | `pdlc post approve` |
| Testing | Approved | Heals | → Verification/Pending | Agent | Yes | |
| Testing | Stale | Valid | TEST | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Verification | Pending | Valid | VERIFY | Agent | Yes | |
| Verification | Review Required | Heals | → Approval Required | Agent | Yes | no persisted review policy |
| Verification | Changes Required | Valid | VERIFY | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Verification | Decision Required | Valid | HUMAN_DECISION | Human | No | |
| Verification | CI Pending | Valid | CI (`pdlc post ci`) | Agent | Yes | genuinely CI-gated — checked, not healed |
| Verification | Approval Required | Valid | HUMAN_APPROVAL | Human | No | completion boundary — `pdlc post complete`, not `post approve` |
| Verification | Approved | Heals | → Complete | — | No | completion boundary special case |
| Verification | Stale | Valid | VERIFY | Agent | Maybe (evidence present and changes are clear; otherwise No) | |
| Complete | Approved (+ Completed lifecycle) | Valid | NONE | — | No | done |
| Complete | any other gate | — | — | — | No | terminal — no other gate is legal |
