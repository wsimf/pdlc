#!/usr/bin/env python3
"""NAME
    pdlc post escalate - park the current stage on a decision only the driver can make

USAGE
    pdlc post escalate WORK_ITEM EVIDENCE_FILE|text:STR|- [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --attachment PATH (repeatable)      attach a local file's contents to the decision comment
    --attachment-description TEXT       description for the --attachment immediately before it

DESCRIPTION
    Records a decision the current stage's owner cannot make itself and moves
    the gate to `Decision Required`, halting autonomous work on the record
    until the driver answers.

    This is the stage owner's counterpart to a reviewer's `pdlc post review
    decision-required`: it runs from a work gate (`Pending`, `Changes
    Required`, or `Stale`) while the stage is still in progress, where a review
    verdict is not yet possible. It posts the evidence through the backend's
    blocker channel under a PDLC-DECISION marker and sets the gate; nothing
    else on the record changes. The evidence body must carry a `## Decision
    Required` section, laid out as `pdlc guide decisions` expects, so the
    driver resolves it with `pdlc post decision` like any other decision. The
    resolution lands the stage back at `Changes Required` with a
    PDLC-RESOLUTION for the owner to reconcile against.

    Refused at any other gate, at `Decision Required` already, on a skipped
    stage, or when the body carries a PDLC marker of its own. A refusal posts
    nothing and changes no state.

EXAMPLES
    pdlc post escalate 142 /tmp/pdlc-implement-decision.md
"""

from __future__ import annotations

import json
import sys

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import Event
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number
from pdlc.internal.inputs import assert_unmarked, print_help, resolve_text, wants_help
from pdlc.internal.workitem import is_stage_skipped, item_for_issue, item_status, post_blocker, set_gate, workflow_for_item
from pdlc.internal.failure import Recovery, report_failure, set_recovery

DECISION_HEADING = "## Decision Required"


def escalate(issue: str, evidence: str, attachment_inputs: list[dict]) -> dict:
    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)
    stage = item_status(record)
    if is_stage_skipped(record, stage):
        raise PdlcError("cannot escalate a stage declared in Skipped States")
    try:
        target = pipeline.next_state(state, Event.ESCALATED)
    except ValueError as error:
        raise PdlcError(str(error)) from None

    body = resolve_text(evidence, label="evidence")
    assert_unmarked(body, "evidence")
    if DECISION_HEADING not in body:
        raise PdlcError(f"an escalation must include a '{DECISION_HEADING}' section")

    attachments = save_attachments(work_item_number(record), attachment_inputs)
    post_blocker(issue, body, "DECISION")
    set_gate(record["id"], target.gate.value)
    return {
        "escalated": True,
        "itemId": record["id"],
        "work_item": int(issue),
        "stage": stage,
        "gateState": target.gate.value,
        "attachments": attachments,
    }


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0
    try:
        args, attachment_inputs = parse_attachment_arguments(command_args)
    except PdlcError as error:
        return report_failure(error)
    if len(args) != 2:
        print("usage: pdlc post escalate WORK_ITEM EVIDENCE_FILE|text:STR|-", file=sys.stderr)
        return 1
    issue, evidence = args
    try:
        set_recovery(Recovery(
            check=f"pdlc inspect {issue}",
            landed="the gate is Decision Required",
            note="A re-run after the PDLC-DECISION comment landed posts a second one; mention it in your report.",
        ))
        result = escalate(issue, evidence, attachment_inputs)
    except PdlcError as error:
        return report_failure(error)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
