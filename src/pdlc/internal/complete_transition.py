"""Complete a PDLC stage by recording its evidence and advancing its gate."""

from __future__ import annotations

from pdlc.internal.attachments import save_attachments, work_item_number  # type: ignore
from pdlc.domain.lifecycle import PdlcError, STAGES, marker_for_stage
from pdlc.internal.workitem import (
    is_stage_skipped,
    item_for_issue,
    item_gate,
    item_status,
    post_comment,
    require_all_subissues_closed,
    set_state,
)


def complete_transition(issue: str, evidence: str, stage: str, attachment_inputs: list[dict] | None = None) -> dict:
    if stage not in STAGES:
        raise PdlcError(f"unsupported completion stage: {stage}")

    record = item_for_issue(issue)
    current_stage = item_status(record)
    current_gate = item_gate(record)
    if current_stage != stage:
        raise PdlcError(f"cannot complete {stage} from {current_stage}")
    if current_gate in ("Review Required", "Approval Required"):
        raise PdlcError(
            f"{stage} is at {current_gate}; it must be invalidated before it can be completed"
        )
    if current_gate not in ("Pending", "Changes Required", "Stale"):
        raise PdlcError(f"cannot complete {stage} from Gate State: {current_gate or 'unset'}")
    if is_stage_skipped(record, stage):
        raise PdlcError(f"{stage} is declared in Skipped States; nothing to complete")
    if stage == "Implementation":
        require_all_subissues_closed(issue)

    gate = "Approval Required" if stage == "Product" else "Review Required"
    attachments = save_attachments(work_item_number(record), attachment_inputs or [])
    post_comment(issue, evidence, marker_for_stage(stage))
    set_state(record["id"], stage, gate, "Planning")

    return {
        "completed": True,
        "itemId": record["id"],
        "work_item": int(issue),
        "stage": stage,
        "gateState": gate,
        "attachments": attachments,
    }
