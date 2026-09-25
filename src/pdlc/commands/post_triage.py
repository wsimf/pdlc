#!/usr/bin/env python3
"""NAME
    pdlc post triage - record a live PR finding and route delivery rework

USAGE
    pdlc post triage WORK_ITEM TARGET EVIDENCE_FILE|text:STR|-

DESCRIPTION
    Records an investigated CI failure or unresolved PR review thread and returns the work item to the delivery stage that owns the fix.

    TARGET is Implementation for a production or task-Result change, or Testing for a test-only or coverage change. The selected workflow must permit re-entry from the current stage. A live failed check or unresolved thread on a registered PR must still exist when this runs; otherwise it refuses without changing the record. The evidence must name the signal and explain why TARGET owns it. On success it posts a PDLC-REVIEW triage note and sets TARGET / Changes Required. Follow that stage's normal pipeline.

    This command does not replace driver-only `pdlc post invalidate`, which changes upstream intent and may retire task evidence.
"""

from __future__ import annotations

import json
import sys

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import Event
from pdlc.internal.invalidation import persist_reentry
from pdlc.internal.inputs import print_help, resolve_text, wants_help
from pdlc.internal.triage import live_signals, signal_ids
from pdlc.internal.workitem import item_for_issue, post_comment, task_tree, workflow_for_item


def triage(issue: str, target_stage: str, evidence: str) -> dict:
    record = item_for_issue(issue)
    pipeline, source = workflow_for_item(record)
    tasks = task_tree(issue)
    signals = live_signals(issue, record, tasks, pipeline, source)
    if not signals.needed:
        raise PdlcError("no live failed check or unresolved review thread on a registered pull request requires triage")
    try:
        target = pipeline.next_state(source, Event.TRIAGED, requested_target=target_stage)
    except ValueError as error:
        raise PdlcError(str(error)) from None
    body = resolve_text(evidence, label="triage evidence")
    identifiers = [f"#{pr['number']}" for pr in signals.failed_prs]
    identifiers += [comment["url"] for comment in signals.comments if comment.get("url")]
    missing = [identifier for identifier in identifiers if identifier not in body]
    if missing:
        raise PdlcError("triage evidence must cite every live failing PR number and unresolved thread URL: " + ", ".join(missing))
    header = "\n".join(f"Triage signal: {identifier}" for identifier in signal_ids(signals))
    note = f"Triage target stage: {target.stage}\nTriage source stage: {source.stage}\n{header}\n\n{body.strip()}\n"
    post_comment(issue, note, "REVIEW")
    persist_reentry(record, target)
    return {"triaged": True, "workItem": int(issue), "from": source.stage,
            "to": target.stage, "gateState": target.gate.value}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(args):
        print_help(__doc__)
        return 0
    if len(args) != 3:
        print("usage: pdlc post triage WORK_ITEM TARGET EVIDENCE_FILE|text:STR|-", file=sys.stderr)
        return 1
    try:
        result = triage(*args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
