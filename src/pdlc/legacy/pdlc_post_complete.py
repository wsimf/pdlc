#!/usr/bin/env python3
"""Final transition: only from Verification / Approval Required, only on
explicit human instruction, and only once `completion_blockers` is empty —
the same policy pdlc-inspect-complete.py reports. This is the one call that
closes a record: it validates the structured completion evidence, posts it,
locks Status/Gate/Lifecycle to Complete/Approved/Completed, and blanks the
now-settled `## Open Questions` section (its real disposition lives in the
evidence). It never otherwise edits the parent body. Only the orchestrator
may call this — gh identity cannot distinguish a human from an agent acting
on their behalf, so this is a procedural boundary, not an authentication check.

    pdlc-post-complete.py WORK_ITEM EVIDENCE_FILE|- [--attachment PATH [--attachment-description TEXT]]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


from pdlc.code_host import get_code_host  # type: ignore
from pdlc.attachments import parse_attachment_arguments, save_attachments, work_item_number  # type: ignore
from pdlc.completion import completion_blockers  # type: ignore
from pdlc.evidence import parse_verification_report  # type: ignore
from pdlc.pdlc_common import PdlcError, print_help, require_file, wants_help  # type: ignore
from pdlc.vcs import stale_commits  # type: ignore
from pdlc.workitem import (  # type: ignore
    comments_for_issue,
    find_marked_comments,
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
)

OPEN_QUESTIONS_SETTLED = "_Resolved at completion — see the completion comment._"


def _read_evidence(evidence: str) -> str:
    """Completion evidence is a file path or `-` for stdin — never an inline
    literal, so a mistyped path fails loudly instead of being posted as-is."""
    if evidence == "-":
        text = sys.stdin.read()
        if not text.strip():
            raise PdlcError("completion evidence on stdin is empty")
        return text
    return require_file("completion evidence", evidence).read_text()


def _stale_rows(verification_body: str) -> list[str]:
    """Rows in the latest verification comment whose commit anchor no longer
    holds against HEAD. Empty when the body does not parse — the malformed
    blocker covers that case."""
    try:
        report = parse_verification_report(verification_body)
    except PdlcError:
        return []
    stale = stale_commits(list(report.verified_commits))
    return [row.text for row in report.rows if row.commit in stale]


def complete(issue: str, evidence: str, attachment_inputs: list[dict]) -> dict:
    evidence_body = _read_evidence(evidence)

    record = item_for_issue(issue)
    body = record.get("issueBody") or ""
    comments = comments_for_issue(issue)

    verification_comments = find_marked_comments(issue, "VERIFICATION", comments=comments)
    verification_body = verification_comments[-1]["body"] if verification_comments else None

    blockers = completion_blockers(
        status=item_status(record),
        gate=item_gate(record),
        tasks=task_tree(issue),
        pull_requests=get_code_host().pull_requests(issue),
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

    attachments = save_attachments(work_item_number(record), attachment_inputs)
    post_comment(issue, evidence_body, "COMPLETE")
    set_state(record["id"], "Complete", "Approved", "Completed")
    update_section(issue, "Open Questions", OPEN_QUESTIONS_SETTLED)

    return {"completed": True, "itemId": record["id"], "work_item": int(issue), "attachments": attachments}


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
        print("usage: pdlc-post-complete.py WORK_ITEM EVIDENCE_FILE|-", file=sys.stderr)
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
