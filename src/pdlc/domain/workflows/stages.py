"""Concrete Feature-pipeline `Stage` instances.

Named here, rather than inline in `workflow_feature.py`, so any module can
read a stage's own policy (e.g. its `skill`) independent of which pipeline —
today only Feature, potentially Bug later — assembles it into a stage list.
"""

from __future__ import annotations

from pdlc.domain.stages import Action, Gate, ReviewerTarget, ReviewPolicy, Stage

PRODUCT_STAGE = Stage(
    name="Product",
    marker="PRODUCT",
    action=Action.HUMAN_INPUT,
    autonomous=False,
    result_gate=Gate.APPROVAL_REQUIRED,
    reason="product artifact is due; user must invoke pdlc-write interactively, and it is not possible to continue autonomously",
    review=ReviewPolicy(
        ReviewerTarget("The Product artifact", "pdlc-product-reviewer"),
    ),
    skippable=False,
    reauthor_in_place=True,
    skill="pdlc-write",
)

UI_STAGE = Stage(
    name="UI",
    marker="UI",
    action=Action.TASKS,
    autonomous=True,
    result_gate=Gate.APPROVAL_REQUIRED,
    reason="UI or task artifact is due",
    review=ReviewPolicy(
        ReviewerTarget("The parent's UI section and its UJ-* journeys", "pdlc-tasks-reviewer"),
    ),
    reauthor_in_place=True,
    skill="pdlc-tasks",
)

TASKS_STAGE = Stage(
    name="Tasks",
    marker="TASKS",
    action=Action.TASKS,
    autonomous=True,
    result_gate=Gate.APPROVAL_REQUIRED,
    reason="UI or task artifact is due",
    review=ReviewPolicy(
        ReviewerTarget("The delivery tasks", "pdlc-tasks-reviewer"),
    ),
    reauthor_in_place=True,
    skill="pdlc-tasks",
)

TECHNICAL_PLAN_STAGE = Stage(
    name="Technical Plan",
    marker="PLAN",
    action=Action.PLAN,
    autonomous=True,
    result_gate=Gate.APPROVAL_REQUIRED,
    reason="technical plan is due",
    review=ReviewPolicy(
        ReviewerTarget("The Technical Plan on each incomplete task", "pdlc-plan-reviewer"),
    ),
    reauthor_in_place=True,
    skill="pdlc-plan",
)

IMPLEMENTATION_STAGE = Stage(
    name="Implementation",
    marker="IMPLEMENTATION",
    action=Action.IMPLEMENT,
    autonomous=True,
    result_gate=Gate.REVIEW_REQUIRED,
    reason="next eligible delivery task is due",
    review=ReviewPolicy(
        ReviewerTarget("Production PRs and each task's implementation", "pdlc-implementation-reviewer"),
    ),
    ci_gated=True,
    skill="pdlc-implement",
)

TESTING_STAGE = Stage(
    name="Testing",
    marker="TESTING",
    action=Action.TEST,
    autonomous=True,
    result_gate=Gate.REVIEW_REQUIRED,
    reason="acceptance coverage is due",
    review=ReviewPolicy(
        ReviewerTarget("Test PRs, coverage, and requirement traceability", "pdlc-testing-reviewer"),
    ),
    ci_gated=True,
    skill="pdlc-test",
)

VERIFICATION_STAGE = Stage(
    name="Verification",
    marker="REVIEW",
    action=Action.VERIFY,
    autonomous=True,
    result_gate=None,
    reason="verification is due",
    accepts_verification=True,
    ci_gated=True,
    skill="pdlc-verify",
)

COMPLETE_STAGE = Stage(
    name="Complete",
    marker=None,
    action=None,
    autonomous=False,
    result_gate=None,
    skippable=False,
    terminal=True,
)
