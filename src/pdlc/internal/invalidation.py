"""Return a stage to Stale.

Shared by pdlc-post-invalidate.py (driver-run) and pdlc-post-verify.py's --bounce
(autonomous, on a Verification "Changes Required" run). Both post one
PDLC-INVALIDATED comment whose body opens with a script-owned
`Invalidated stage: <STAGE>` line, drop the stage to Stale, and clear it from
Skipped States so the next routing pass does not bypass it straight back to
Stale.
"""

from __future__ import annotations

from pdlc.domain.lifecycle import STAGES, PdlcError
from pdlc.internal.workitem import (
    is_stage_skipped,
    item_skipped_states,
    item_status,
    post_comment,
    set_skipped_states,
    set_state,
)


# The pre-publication stages: reviewed on local files before they land, so they
# reach Approval Required directly and are reworked by returning to Stale.
REAUTHOR_STAGES = ("Product", "UI", "Tasks", "Technical Plan")


def reauthor_invalidate_stage(record: dict, stage: str) -> None:
    """Silently return a pre-publication stage from Approval Required to Stale so
    its owning skill can re-land a reviewed artifact in the same call.

    Used only by pdlc-post-write.py / pdlc-post-tasks.py / pdlc-post-plan.py when
    the driver asks for a change before the stage's approval gate has cleared.
    No comment is posted: the re-land's own `PDLC-PRODUCT` / `PDLC-TASKS` /
    `PDLC-PLAN` evidence records the change, and the stage never settled at
    `Approved`, so there is nothing to invalidate — only a gate reset. Nothing
    here feeds the rework/churn count.
    """
    if stage not in REAUTHOR_STAGES:
        raise PdlcError(f"stage is not re-authored in place: {stage}")

    current = item_status(record)
    if current != stage:
        raise PdlcError(f"cannot re-author {stage}: record is at {current or 'unset'}")

    set_state(record["id"], stage, "Stale", "Planning")


def invalidate_stage(issue: str, record: dict, stage: str, evidence_body: str) -> None:
    if stage not in STAGES:
        raise PdlcError(f"unsupported invalidation stage: {stage}")

    # A completed record is locked: its evidence shipped, so nothing may reopen
    # it, and no invalidation may target a stage the record has not reached yet.
    current = item_status(record)
    if current == "Complete":
        raise PdlcError("record is Complete and locked; it cannot be invalidated")
    if current not in STAGES:
        raise PdlcError(f"cannot invalidate from an unset or unknown Status: {current or 'unset'}")
    if STAGES.index(stage) > STAGES.index(current):
        raise PdlcError(f"cannot invalidate {stage}: it is downstream of the active stage {current}")

    body = f"Invalidated stage: {stage}\n\n{evidence_body.strip()}\n"
    post_comment(str(issue), body, "INVALIDATED")
    set_state(record["id"], stage, "Stale", "Planning")

    if is_stage_skipped(record, stage):
        remaining = [
            state for state in item_skipped_states(record).split(",") if state and state != stage
        ]
        set_skipped_states(record["id"], ",".join(remaining))
