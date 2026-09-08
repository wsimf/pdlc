#!/usr/bin/env python3
"""Records explicit human approval of the current stage and advances the
work item to the next stage's Pending. Refuses Verification — that
transition is completion, handled by pdlc post complete instead. Only the
orchestrator may call this, and only on an explicit human instruction — gh
identity cannot distinguish a human from an agent acting on their behalf, so
this is a procedural boundary, not an authentication check.

    pdlc post approve WORK_ITEM EVIDENCE_FILE|- [--attachment PATH [--attachment-description TEXT]]
"""

from __future__ import annotations

import json
import sys


from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help
from pdlc.domain.workflow import Event
from pdlc.internal.workitem import (
    current_actor,
    is_stage_skipped,
    item_for_issue,
    item_gate,
    item_status,
    post_comment,
    set_state,
    workflow_for_item,
)


def approve(issue: str, evidence: str, attachment_inputs: list[dict]) -> dict:
    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)
    stage = item_status(record)

    if item_gate(record) != "Approval Required":
        raise PdlcError("approval requires Gate State = Approval Required")
    if is_stage_skipped(record, stage):
        raise PdlcError(f"{stage} is declared in Skipped States; nothing to approve")
    try:
        target = pipeline.next_state(state, Event.APPROVED)
    except ValueError as error:
        if pipeline.completion_policy is not None and pipeline.completion_policy.is_boundary(state):
            raise PdlcError(f"use pdlc post complete after {stage} approval") from None
        raise PdlcError(str(error)) from None

    login = current_actor()

    attachments = save_attachments(work_item_number(record), attachment_inputs)
    post_comment(issue, evidence, "APPROVED")
    set_state(record["id"], target.stage, target.gate.value, target.lifecycle.value)

    return {
        "approved": True,
        "itemId": record["id"],
        "work_item": int(issue),
        "actor": login,
        "from": stage,
        "to": target.stage,
        "gateState": target.gate.value,
        "attachments": attachments,
    }


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw_args = command_args
    if wants_help(raw_args):
        print_help(__doc__)
        return 0
    try:
        args, attachment_inputs = parse_attachment_arguments(raw_args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    if len(args) != 2:
        print("usage: pdlc post approve WORK_ITEM EVIDENCE_FILE|-", file=sys.stderr)
        return 1
    issue, evidence = args

    try:
        result = approve(issue, evidence, attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
