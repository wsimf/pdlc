"""Feature pipeline wiring.

The Feature pipeline is deliberately an ordered spine: its stage list,
completion policy, invalidation policy, and rework policy are declared here
as data over the generic engine in `workflow.py`. Registration alongside the
Bug pipeline happens in `pipeline.py`.
"""

from __future__ import annotations

from pdlc.domain.workflow import (
    REQUESTED_TARGET,
    CompletionPolicy,
    Event,
    Gate,
    InvalidationPolicy,
    Lifecycle,
    Pipeline,
    ReworkPolicy,
    TransitionOverride,
    WorkType,
)
from pdlc.domain.workflows.stages import (
    COMPLETE_STAGE,
    IMPLEMENTATION_STAGE,
    PRODUCT_STAGE,
    TASKS_STAGE,
    TECHNICAL_PLAN_STAGE,
    TESTING_STAGE,
    UI_STAGE,
    VERIFICATION_STAGE,
)

_FEATURE_STAGES = (
    PRODUCT_STAGE,
    UI_STAGE,
    TASKS_STAGE,
    TECHNICAL_PLAN_STAGE,
    IMPLEMENTATION_STAGE,
    TESTING_STAGE,
    VERIFICATION_STAGE,
    COMPLETE_STAGE,
)
_FEATURE_ACTIVE_STAGES = tuple(stage.name for stage in _FEATURE_STAGES if not stage.terminal)

_FEATURE_COMPLETION_POLICY = CompletionPolicy(
    boundary_stage="Verification",
    boundary_gate=Gate.APPROVAL_REQUIRED,
    required_stage_evidence=(
        "Product",
        "UI",
        "Tasks",
        "Technical Plan",
        "Implementation",
        "Testing",
    ),
    require_stage_settlement=True,
    require_tasks_closed=True,
    require_task_implementation=True,
    require_prs_merged=True,
    require_checks_green=True,
    verification_parser="parse_verification_report",
)

_FEATURE_INVALIDATION_POLICY = InvalidationPolicy(
    evidence_dependencies={
        "Product": ("UI", "Tasks", "Technical Plan", "Implementation", "Testing", "Verification"),
        "UI": ("Tasks", "Technical Plan", "Implementation", "Testing", "Verification"),
        "Tasks": ("Technical Plan", "Implementation", "Testing", "Verification"),
        "Technical Plan": ("Implementation", "Testing", "Verification"),
        "Implementation": ("Testing", "Verification"),
        "Testing": ("Verification",),
        "Verification": (),
    },
    reentry_targets={
        "Product": ("Product",),
        "UI": ("Product", "UI"),
        "Tasks": ("Product", "UI", "Tasks"),
        "Technical Plan": ("Product", "UI", "Tasks", "Technical Plan"),
        "Implementation": ("Product", "UI", "Tasks", "Technical Plan", "Implementation"),
        "Testing": ("Product", "UI", "Tasks", "Technical Plan", "Implementation", "Testing"),
        "Verification": ("Implementation", "Testing"),
    },
)

FEATURE_PIPELINE = Pipeline(
    work_type=WorkType.FEATURE,
    stages=_FEATURE_STAGES,
    overrides=(
        TransitionOverride("Verification", Gate.PENDING, Event.SKIPPED, "Verification", Gate.APPROVAL_REQUIRED),
        TransitionOverride("Verification", Gate.CHANGES_REQUIRED, Event.SKIPPED, "Verification", Gate.APPROVAL_REQUIRED),
        TransitionOverride("Verification", Gate.STALE, Event.SKIPPED, "Verification", Gate.APPROVAL_REQUIRED),
        TransitionOverride("Verification", Gate.CHANGES_REQUIRED, Event.BOUNCED, REQUESTED_TARGET, Gate.STALE, Lifecycle.PLANNING, loop="delivery-rework"),
        TransitionOverride("Verification", Gate.APPROVAL_REQUIRED, Event.BOUNCED, REQUESTED_TARGET, Gate.STALE, Lifecycle.PLANNING, loop="delivery-rework"),
    ),
    completion_policy=_FEATURE_COMPLETION_POLICY,
    invalidation_policy=_FEATURE_INVALIDATION_POLICY,
    rework_policy=ReworkPolicy("delivery-rework", 3, ("Implementation", "Testing"), "Verification"),
)
