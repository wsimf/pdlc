#!/usr/bin/env python3
"""Returns a stage to Stale when upstream intent changed, without touching
downstream artifacts — they stay in place but their evidence is now
considered invalid until the owning stage reconciles them.

The posted PDLC-INVALIDATED comment opens with a script-owned
`Invalidated stage: <STAGE>` line before the caller's evidence, so the
comment history — not just the current work-item state — records which stage
each invalidation returned to Stale.

    pdlc-post-invalidate.py WORK_ITEM STAGE EVIDENCE_FILE|- [--attachment PATH [--attachment-description TEXT]]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


from pdlc.attachments import parse_attachment_arguments, save_attachments, work_item_number  # type: ignore
from pdlc.pdlc_common import PdlcError, evidence_source, print_help, wants_help  # type: ignore
from pdlc.invalidation import invalidate_stage  # type: ignore
from pdlc.workitem import item_for_issue  # type: ignore


def invalidate(issue: str, stage: str, evidence: str, attachment_inputs: list[dict]) -> dict:
    record = item_for_issue(issue)

    # The STAGE argv drives the state change; invalidate_stage also stamps an
    # `Invalidated stage: <STAGE>` line into the comment so history — not just
    # the transient work-item state — records which stage each PDLC-INVALIDATED
    # comment returned to Stale, which the churn detector reads back.
    path, is_temporary = evidence_source("evidence", evidence)
    try:
        evidence_body = path.read_text()
    finally:
        if is_temporary:
            path.unlink(missing_ok=True)

    attachments = save_attachments(work_item_number(record), attachment_inputs)
    invalidate_stage(issue, record, stage, evidence_body)

    return {"invalidated": True, "itemId": record["id"], "work_item": int(issue), "stage": stage, "gateState": "Stale", "attachments": attachments}


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
    if len(args) != 3:
        print("usage: pdlc-post-invalidate.py WORK_ITEM STAGE EVIDENCE_FILE|-", file=sys.stderr)
        return 1
    issue, stage, evidence = args

    try:
        result = invalidate(issue, stage, evidence, attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
