"""Return a stage to Stale.

Driver invalidation posts PDLC-INVALIDATED. Verification bounce provenance is
already captured by PDLC-REVIEW, so it only persists the authorized re-entry.
"""

from __future__ import annotations

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import Event, Pipeline, State
from pdlc.internal.workitem import (
    is_stage_skipped,
    item_skipped_states,
    item_status,
    pipeline_for_item,
    post_comment,
    reopen_task,
    set_skipped_states,
    set_state,
    state_for_item,
    subissues_for,
)

# Stages whose evidence lives on the delivery tasks themselves rather than the
# record body, so invalidating back onto one can mean reopening tasks Implementation
# had already closed.
TASK_SCOPED_STAGES = ("Technical Plan", "Implementation")


def reauthor_invalidate_stage(record: dict, stage: str, pipeline: Pipeline) -> None:
    """Silently return a pre-publication stage from Approval Required to Stale so
    its owning skill can re-land a reviewed artifact in the same call.

    Used only by pdlc post write / pdlc post tasks / pdlc post plan when
    the driver asks for a change before the stage's approval gate has cleared.
    No comment is posted: the re-land's own `PDLC-PRODUCT` / `PDLC-TASKS` /
    `PDLC-PLAN` evidence records the change, and the stage never settled at
    `Approved`, so there is nothing to invalidate — only a gate reset. Nothing
    here feeds the rework/churn count.
    """
    current = item_status(record)
    if current != stage:
        raise PdlcError(f"cannot re-author {stage}: record is at {current or 'unset'}")

    state = state_for_item(record, pipeline)
    try:
        target = pipeline.next_state(state, Event.REAUTHORED)
    except ValueError as error:
        raise PdlcError(str(error)) from None
    set_state(record["id"], target.stage, target.gate.value, target.lifecycle.value)
    record["Status"] = target.stage
    record["Gate State"] = target.gate.value
    record["Lifecycle"] = target.lifecycle.value


def _persist_reentry(record: dict, target: State) -> None:
    set_state(record["id"], target.stage, target.gate.value, target.lifecycle.value)

    if is_stage_skipped(record, target.stage):
        remaining = [
            state for state in item_skipped_states(record).split(",") if state and state != target.stage
        ]
        set_skipped_states(record["id"], ",".join(remaining))


def _record_invalidation(issue: str, record: dict, target: State, evidence_body: str) -> None:
    body = f"Invalidated stage: {target.stage}\n\n{evidence_body.strip()}\n"
    post_comment(str(issue), body, "INVALIDATED")
    _persist_reentry(record, target)


def bounce_stage(record: dict, pipeline: Pipeline, source: State, stage: str) -> State:
    """Persist a pipeline-authorized Verification re-entry."""
    try:
        target = pipeline.next_state(source, Event.BOUNCED, requested_target=stage)
    except ValueError as error:
        raise PdlcError(str(error)) from None
    _persist_reentry(record, target)
    return target


def _reopen_tasks(issue: str, target_stage: str, task_refs: list[str] | None) -> list[str]:
    """Reopen closed delivery tasks so they are back in scope for the
    invalidated stage's own gate (e.g. `needsPlan`). `task_refs` narrows the
    scope to specific tasks; omitted, every closed task under the record is
    reopened. Returns the numbers actually reopened."""
    tasks = subissues_for(issue)
    if task_refs:
        wanted = {str(ref) for ref in task_refs}
        known = {str(task["number"]) for task in tasks}
        unknown = sorted(wanted - known)
        if unknown:
            raise PdlcError(f"unknown delivery task(s) for #{issue}: {','.join(unknown)}")
        tasks = [task for task in tasks if str(task["number"]) in wanted]

    reopened = []
    for task in tasks:
        if task["state"] != "CLOSED":
            continue
        number = str(task["number"])
        reopen_task(number)
        post_comment(number, f"Invalidated stage: {target_stage}\n\nReopened for rework.\n", "INVALIDATED")
        reopened.append(number)
    return reopened


def invalidate_stage(issue: str, record: dict, stage: str, evidence_body: str, task_refs: list[str] | None = None) -> None:
    # A completed record is locked: its evidence shipped, so nothing may reopen
    # it, and no invalidation may target a stage the record has not reached yet.
    current = item_status(record)
    pipeline = pipeline_for_item(record)
    if current == pipeline.terminal_stage:
        raise PdlcError("record is Complete and locked; it cannot be invalidated")
    source = state_for_item(record, pipeline)
    try:
        target = pipeline.next_state(source, Event.INVALIDATED, requested_target=stage)
    except ValueError as error:
        raise PdlcError(str(error)) from None

    if task_refs and target.stage not in TASK_SCOPED_STAGES:
        raise PdlcError(
            f"--task only applies when invalidating to {' or '.join(TASK_SCOPED_STAGES)}, not {target.stage}"
        )

    _record_invalidation(issue, record, target, evidence_body)

    if target.stage in TASK_SCOPED_STAGES:
        _reopen_tasks(issue, target.stage, task_refs)
