#!/usr/bin/env python3
"""Resolves an Implementation record parked at `CI Pending` against the live
check state of its pull request(s).

    pdlc post ci WORK_ITEM

  - checks still running          -> no change; reports "still running"
  - checks green / none tracked   -> Implementation / Approval Required
  - checks red                    -> posts a PDLC-IMPLEMENTATION note and
                                     Implementation / Changes Required

Mechanical: it records an external fact, makes no judgement, and carries no
identity check. The autonomous loop runs it once CI finishes; a driver may run
it directly when resuming a CI-Pending record. It refuses any other gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


from pdlc.internal.ci_gate import resolve_ci_gate  # type: ignore
from pdlc.domain.lifecycle import PdlcError, print_help, wants_help  # type: ignore
from pdlc.internal.workitem import item_for_issue, item_gate, workflow_for_item  # type: ignore


def post_ci(issue: str) -> dict:
    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)
    if item_gate(record) != "CI Pending":
        raise PdlcError(f"pdlc post ci requires Gate State = CI Pending, not {item_gate(record) or 'unset'}")

    result = resolve_ci_gate(issue, record, pipeline, state)
    return {"workItem": int(issue), "itemId": record["id"], "stage": state.stage, **result}


def main() -> int:
    args = sys.argv[1:]
    if wants_help(args):
        print_help(__doc__)
        return 0
    if len(args) != 1:
        print("usage: pdlc post ci WORK_ITEM", file=sys.stderr)
        return 1

    try:
        result = post_ci(args[0])
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
