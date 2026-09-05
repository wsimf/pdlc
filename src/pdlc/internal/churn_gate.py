"""Churn-gated autonomous advancement.

Once a record has demonstrably iterated the rework loop, the human approval
steps on Implementation and Testing are dropped: the script that would
otherwise park the record at `Approval Required` writes straight past the gate
instead, posting a PDLC-AUTOAPPROVED comment and advancing to the next stage's
`Pending`. On-disk state is always real — nothing is deferred to a later
routing pass.

The loop count is the number of structured Verification reviews that record a
Changes Required bounce into this pipeline's rework loop. Driver invalidations
do not count. Auto-approval fires while that count is 1..cap; past the cap
the gate stops for the driver again, which naturally terminates an autonomous
run. Verification approval is never auto-cleared — its approval is the
completion boundary. Each pipeline's rework policy owns its cap.
"""

from __future__ import annotations

from pdlc.domain.model import review_rework_count
from pdlc.domain.workflow import Event, Pipeline, State
from pdlc.internal.workitem import comments_for_issue, post_comment, set_state


# Verification bounces recorded for this pipeline's named rework loop.
def rework_loops(issue: str, pipeline: Pipeline) -> int:
    policy = pipeline.rework_policy
    if policy is None:
        return 0
    return review_rework_count(comments_for_issue(str(issue)), policy.name)


# Clears an Implementation/Testing Approval Required gate with no human step when
# the record has been reworked between 1 and cap times. Writes the advance itself
# and returns the landed state notation; on the first pass, past the cap, or when
# disabled it writes nothing and returns None, leaving the caller to record
# `Approval Required` as usual.
def autoapprove_stage(issue: str, record: dict, pipeline: Pipeline, state: State) -> str | None:
    policy = pipeline.rework_policy
    if policy is None:
        return None
    loops = rework_loops(issue, pipeline)
    if not pipeline.can_autoapprove(state.stage, loops):
        return None

    target = pipeline.next_state(state, Event.AUTOAPPROVED)
    post_comment(
        str(issue),
        f"Auto-approved {state.stage} without human review: the record has been reworked "
        f"{loops} time(s), within the autonomous limit of {policy.max_iterations}. "
        f"Advancing to {target.stage} / {target.gate.value}. Verification approval still stops for the driver.",
        "AUTOAPPROVED",
    )
    set_state(record["id"], target.stage, target.gate.value, target.lifecycle.value)
    return f"{target.stage} / {target.gate.value}"
