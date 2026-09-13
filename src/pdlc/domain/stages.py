"""Pipeline-agnostic stage declarations.

`Gate`, `Action`, and `Stage` (plus its review types) carry no dependency on
any specific pipeline wiring, so they live here rather than alongside the
generic transition engine or a pipeline's own stage list — any module may
import them without pulling in `Pipeline` or a work type's stage data.

Concrete `Stage` instances (data) live under `domain/workflows/` instead,
e.g. `workflows/stages.py`, so a work type's stage data never mixes with
these pipeline-agnostic blueprints.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Gate(StrEnum):
    PENDING = "Pending"
    REVIEW_REQUIRED = "Review Required"
    CHANGES_REQUIRED = "Changes Required"
    DECISION_REQUIRED = "Decision Required"
    CI_PENDING = "CI Pending"
    APPROVAL_REQUIRED = "Approval Required"
    APPROVED = "Approved"
    STALE = "Stale"


class Action(StrEnum):
    NONE = "none"
    BLOCKED = "blocked"
    HUMAN_INPUT = "human-input"
    HUMAN_APPROVAL = "human-approval"
    HUMAN_DECISION = "human-decision"
    REVIEW = "pdlc-review"
    CI = "pdlc-post-ci"
    TASKS = "pdlc-tasks"
    PLAN = "pdlc-plan"
    IMPLEMENT = "pdlc-implement"
    TEST = "pdlc-test"
    VERIFY = "pdlc-verify"
    CONTINUE = "pdlc-continue"


@dataclass(frozen=True)
class ReviewerTarget:
    """The artifact and specialist that own an independent review."""

    artifact: str
    agent: str

    @property
    def reviewer(self) -> str:
        return self.agent


@dataclass(frozen=True)
class ReviewPolicy:
    """Review behavior for a stage that requires an independent review."""

    target: ReviewerTarget | None = None
    clean_gate: Gate = Gate.APPROVAL_REQUIRED


@dataclass(frozen=True)
class Stage:
    """Policy attached to one stage in a pipeline."""

    name: str
    # The evidence comment marker (`PDLC-{marker}`) that proves this stage
    # settled — None only for the terminal stage, which writes no evidence.
    marker: str | None
    # The routing verb for this stage's *own* work gates (Pending, Changes
    # Required, Stale) — None only for the terminal stage. Independent of
    # `skill`: this can be human-input/human-approval, not always a skill.
    action: Action | None
    # Whether `action` can run without driver confirmation each time.
    autonomous: bool
    # The gate a clean Published/Reviewed/CI outcome lands on next — None
    # when the stage has no single successor gate (e.g. Verification, whose
    # outcome always routes through an explicit event).
    result_gate: Gate | None
    reason: str = ""
    # Independent-review policy, or None when the stage has no review step.
    review: ReviewPolicy | None = None
    # Whether this stage's Review Required outcome must pass through CI
    # Pending before Approval Required, rather than going straight there.
    ci_gated: bool = False
    # Whether a driver may skip this stage entirely via Event.SKIPPED.
    skippable: bool = True
    # Whether a driver request to change this artifact re-enters its owning
    # skill in place (Approval Required → Stale) instead of restarting the
    # stage from Pending.
    reauthor_in_place: bool = False
    # Whether this stage is the one Verification's outcome (clean/findings/
    # decision) is written onto — true only for Verification itself.
    accepts_verification: bool = False
    # Whether this is the pipeline's terminal stage: no action, marker,
    # review, or skill may be declared alongside it.
    terminal: bool = False
    # The pdlc-* skill that produces or redoes this stage's own artifact —
    # distinct from `action`, which is the routing verb for the *current*
    # gate (also human-input/human-approval/etc, not always a skill name).
    # Lets callers (e.g. a due-next message, or a rework dispatch) look up
    # "what do I run to redo this stage" from data instead of special-casing
    # a stage by name.
    skill: str | None = None
