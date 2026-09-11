#!/usr/bin/env python3
"""NAME
    pdlc post complete - final transition: lock a verified record to Complete

USAGE
    pdlc post complete WORK_ITEM EVIDENCE_FILE|- [--attachment PATH [--attachment-description TEXT]]

DESCRIPTION
    Final transition: only from Verification / Approval Required, only on
    explicit human instruction, and only once `completion_blockers` is empty —
    the same policy pdlc inspect complete reports. This is the one call that
    closes a record: it validates the structured completion evidence, posts it,
    locks Status/Gate/Lifecycle to Complete/Approved/Completed, and blanks the
    now-settled `## Open Questions` section (its real disposition lives in the
    evidence). It never otherwise edits the parent body. Only the orchestrator
    may call this — gh identity cannot distinguish a human from an agent acting
    on their behalf, so this is a procedural boundary, not an authentication check.
"""

from __future__ import annotations

import json
import sys


from pdlc.internal.pull_requests import record_pull_requests
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number
from pdlc.domain.completion import completion_blockers
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import resolve_text, print_help, wants_help
from pdlc.domain.workflow import Event
from pdlc.internal.vcs import stale_verification_rows
from pdlc.internal.workitem import (
    comments_for_issue,
    item_for_issue,
    item_gate,
    item_skipped_states,
    item_status,
    marked_comments,
    post_comment,
    read_section,
    set_state,
    task_tree,
    update_section,
    verification_evidence_comments,
    workflow_for_item,
)

OPEN_QUESTIONS_SETTLED = "_Resolved at completion — see the completion comment._"


def _stale_rows(verification_body: str) -> list[str]:
    """Rows in the latest verification comment whose commit anchor no longer
    holds against HEAD. Empty when the body does not parse — the malformed
    blocker covers that case."""
    try:
        return stale_verification_rows(verification_body)
    except PdlcError:
        return []


def complete(issue: str, evidence: str, attachment_inputs: list[dict]) -> dict:
    evidence_body = resolve_text(evidence, label="completion evidence")

    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)
    body = record.get("issueBody") or ""
    comments = comments_for_issue(issue)

    verification_comments = verification_evidence_comments(issue, comments=comments)
    verification_body = verification_comments[-1]["body"] if verification_comments else None

    tasks = task_tree(issue)
    blockers = completion_blockers(
        pipeline=pipeline,
        status=item_status(record),
        gate=item_gate(record),
        tasks=tasks,
        pull_requests=record_pull_requests(issue, record=record, tasks=tasks),
        timeline_markers=[comment["marker"] for comment in marked_comments(issue, comments=comments)],
        skipped_states=item_skipped_states(record),
        verification_body=verification_body,
        stale_rows=_stale_rows(verification_body) if verification_body else None,
        open_questions=read_section(body, "Open Questions"),
        evidence_body=evidence_body,
    )
    if blockers:
        raise PdlcError(
            "record is not ready to complete:\n"
            + "\n".join(f"  - [{blocker.code}] {blocker.message}" for blocker in blockers)
        )
    try:
        target = pipeline.next_state(state, Event.COMPLETED)
    except ValueError as error:
        raise PdlcError(str(error)) from None

    attachments = save_attachments(work_item_number(record), attachment_inputs)
    post_comment(issue, evidence_body, "COMPLETE")
    set_state(record["id"], target.stage, target.gate.value, target.lifecycle.value)
    update_section(issue, "Open Questions", OPEN_QUESTIONS_SETTLED)

    return {"completed": True, "itemId": record["id"], "work_item": int(issue), "attachments": attachments}


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
        print("usage: pdlc post complete WORK_ITEM EVIDENCE_FILE|-", file=sys.stderr)
        return 1
    issue, evidence = args

    try:
        result = complete(issue, evidence, attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
