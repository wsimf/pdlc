#!/usr/bin/env python3
"""Returns a stage to Stale when upstream intent changed, without touching
downstream artifacts — they stay in place but their evidence is now
considered invalid until the owning stage reconciles them.

The posted PDLC-INVALIDATED comment opens with a script-owned
`Invalidated stage: <STAGE>` line before the caller's evidence, so the
comment history — not just the current work-item state — records which stage
each invalidation returned to Stale.

Invalidating to Technical Plan or Implementation also reopens delivery tasks
Implementation had already closed, so they are back in scope for re-planning
or re-implementation; each reopened task gets its own PDLC-INVALIDATED
comment. `--task` (repeatable) narrows this to specific task numbers; omitted,
every closed task under the record is reopened. `--task` on any other target
stage is rejected — those stages carry no per-task evidence to reopen.

    pdlc post invalidate WORK_ITEM STAGE EVIDENCE_FILE|text:STR|- [--task TASK_NUMBER ...] [--attachment PATH [--attachment-description TEXT]]
"""

from __future__ import annotations

import json
import sys


from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, resolve_text, wants_help
from pdlc.internal.invalidation import invalidate_stage
from pdlc.internal.workitem import item_for_issue


def _parse_task_arguments(argv: list[str]) -> tuple[list[str], list[str]]:
    """Extract repeated `--task TASK_NUMBER` pairs."""
    remaining: list[str] = []
    tasks: list[str] = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument != "--task":
            remaining.append(argument)
            index += 1
            continue
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            raise PdlcError("--task requires a delivery task number")
        tasks.append(argv[index + 1])
        index += 2
    return remaining, tasks


def invalidate(issue: str, stage: str, evidence: str, attachment_inputs: list[dict], task_refs: list[str] | None = None) -> dict:
    record = item_for_issue(issue)

    # The STAGE argv drives the state change; invalidate_stage also stamps an
    # `Invalidated stage: <STAGE>` line into the comment so history — not just
    # the transient work-item state — records which stage the driver returned
    # to Stale. Verification rework loops are tracked separately by PDLC-REVIEW.
    evidence_body = resolve_text(evidence, label="evidence")

    attachments = save_attachments(work_item_number(record), attachment_inputs)
    invalidate_stage(issue, record, stage, evidence_body, task_refs)

    return {"invalidated": True, "itemId": record["id"], "work_item": int(issue), "stage": stage, "gateState": "Stale", "attachments": attachments}


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw_args = command_args
    if wants_help(raw_args):
        print_help(__doc__)
        return 0
    try:
        args, attachment_inputs = parse_attachment_arguments(raw_args)
        args, task_refs = _parse_task_arguments(args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    if len(args) != 3:
        print("usage: pdlc post invalidate WORK_ITEM STAGE EVIDENCE_FILE|text:STR|-", file=sys.stderr)
        return 1
    issue, stage, evidence = args

    try:
        result = invalidate(issue, stage, evidence, attachment_inputs, task_refs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
