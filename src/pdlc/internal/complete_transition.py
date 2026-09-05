"""Complete a PDLC stage by recording its evidence and advancing its gate."""

from __future__ import annotations

from dataclasses import dataclass

from pdlc.internal.attachments import save_attachments, work_item_number  # type: ignore
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import Event, Pipeline, State
from pdlc.internal.workitem import (
    is_stage_skipped,
    item_for_issue,
    item_gate,
    item_status,
    post_comment,
    require_all_subissues_closed,
    set_state,
    workflow_for_item,
)


@dataclass(frozen=True)
class Publication:
    issue: str
    record: dict
    pipeline: Pipeline
    target: State


def prepare_transition(issue: str, stage: str) -> Publication:
    """Validate publication before callers perform PR or evidence writes."""
    record = item_for_issue(issue)
    current_stage = item_status(record)
    current_gate = item_gate(record)
    if current_stage != stage:
        raise PdlcError(f"cannot complete {stage} from {current_stage}")
    if is_stage_skipped(record, stage):
        raise PdlcError(f"{stage} is declared in Skipped States; nothing to complete")
    if stage == "Implementation":
        require_all_subissues_closed(issue)

    pipeline, state = workflow_for_item(record)
    try:
        target = pipeline.next_state(state, Event.PUBLISHED)
    except ValueError as error:
        if current_gate in ("Review Required", "Approval Required"):
            raise PdlcError(f"{stage} is at {current_gate}; it must be invalidated before it can be completed") from None
        raise PdlcError(str(error)) from None

    return Publication(issue, record, pipeline, target)


def complete_transition(publication: Publication, evidence: str, attachment_inputs: list[dict] | None = None) -> dict:
    issue, record = publication.issue, publication.record
    pipeline, target = publication.pipeline, publication.target
    stage = item_status(record)
    attachments = save_attachments(work_item_number(record), attachment_inputs or [])
    post_comment(issue, evidence, pipeline.marker_for_stage(stage))
    set_state(record["id"], target.stage, target.gate.value, target.lifecycle.value)

    return {
        "completed": True,
        "itemId": record["id"],
        "work_item": int(issue),
        "stage": stage,
        "gateState": target.gate.value,
        "attachments": attachments,
    }
