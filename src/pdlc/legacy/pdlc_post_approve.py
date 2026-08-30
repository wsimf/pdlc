#!/usr/bin/env python3
"""Records explicit human approval of the current stage and advances the
work item to the next stage's Pending. Refuses Verification — that
transition is completion, handled by pdlc-post-complete.py instead. Only the
orchestrator may call this, and only on an explicit human instruction — gh
identity cannot distinguish a human from an agent acting on their behalf, so
this is a procedural boundary, not an authentication check.

    pdlc-post-approve.py WORK_ITEM EVIDENCE_FILE|- [--attachment PATH [--attachment-description TEXT]]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


from pdlc.attachments import parse_attachment_arguments, save_attachments, work_item_number  # type: ignore
from pdlc.pdlc_common import PdlcError, next_stage, print_help, wants_help  # type: ignore
from pdlc.workitem import (  # type: ignore
    current_actor,
    is_stage_skipped,
    item_for_issue,
    item_gate,
    item_status,
    post_comment,
    set_state,
)


def approve(issue: str, evidence: str, attachment_inputs: list[dict]) -> dict:
    record = item_for_issue(issue)
    stage = item_status(record)
    next_stage_value = next_stage(stage)

    if item_gate(record) != "Approval Required":
        raise PdlcError("approval requires Gate State = Approval Required")
    if stage == "Verification":
        raise PdlcError("use pdlc-post-complete.py after Verification approval")
    if is_stage_skipped(record, stage):
        raise PdlcError(f"{stage} is declared in Skipped States; nothing to approve")

    login = current_actor()

    attachments = save_attachments(work_item_number(record), attachment_inputs)
    post_comment(issue, evidence, "APPROVED")
    set_state(record["id"], next_stage_value, "Pending", "Planning")

    return {
        "approved": True,
        "itemId": record["id"],
        "work_item": int(issue),
        "actor": login,
        "from": stage,
        "to": next_stage_value,
        "gateState": "Pending",
        "attachments": attachments,
    }


def main() -> int:
    raw_args = sys.argv[1:]
    if wants_help(raw_args):
        print_help(__doc__)
        return 0
    try:
        args, attachment_inputs = parse_attachment_arguments(raw_args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    if len(args) != 2:
        print("usage: pdlc-post-approve.py WORK_ITEM EVIDENCE_FILE|-", file=sys.stderr)
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
