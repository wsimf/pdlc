"""Churn-gated autonomous advancement.

Once a record has demonstrably iterated the rework loop, the human approval
steps on Implementation and Testing are dropped: the script that would
otherwise park the record at `Approval Required` writes straight past the gate
instead, posting a PDLC-AUTOAPPROVED comment and advancing to the next stage's
`Pending`. On-disk state is always real — nothing is deferred to a later
routing pass.

The loop count is the total number of `Invalidated stage: <STAGE>` events in
comment history, across every stage — one full rework (a Verification bounce to
Implementation, Testing, or the plan; a driver invalidation) adds one, whichever
stage it targeted. Auto-approval fires while that count is 1..cap; past the cap
the gate stops for the driver again, which naturally terminates an autonomous
run. Verification approval is never auto-cleared — its approval is the
completion boundary. PDLC_AUTOAPPROVE_CHURN_CAP=0 disables it.
"""

from __future__ import annotations

import os

from pdlc_common import next_stage
from pdlc_model import invalidations_by_stage
from workitem import comments_for_issue, post_comment, set_state

AUTOAPPROVE_STAGES = ("Implementation", "Testing")


def churn_cap() -> int:
    return int(os.environ.get("PDLC_AUTOAPPROVE_CHURN_CAP", "3"))


# Total returns-to-Stale recorded in comment history, across all stages. Each is
# one pass through the rework loop regardless of which stage it bounced to.
def rework_loops(issue: str) -> int:
    return sum(invalidations_by_stage(comments_for_issue(str(issue))).values())


# Clears an Implementation/Testing Approval Required gate with no human step when
# the record has been reworked between 1 and cap times. Writes the advance itself
# and returns the landed state notation; on the first pass, past the cap, or when
# disabled it writes nothing and returns None, leaving the caller to record
# `Approval Required` as usual.
def autoapprove_stage(issue: str, record: dict, stage: str) -> str | None:
    if stage not in AUTOAPPROVE_STAGES:
        return None
    cap = churn_cap()
    loops = rework_loops(issue)
    if cap <= 0 or not (1 <= loops <= cap):
        return None

    target = next_stage(stage)
    post_comment(
        str(issue),
        f"Auto-approved {stage} without human review: the record has been reworked "
        f"{loops} time(s), within the autonomous limit of {cap}. "
        f"Advancing to {target} / Pending. Verification approval still stops for the driver.",
        "AUTOAPPROVED",
    )
    set_state(record["id"], target, "Pending", "Planning")
    return f"{target} / Pending"
