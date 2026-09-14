#!/usr/bin/env python3
"""NAME
    pdlc continue - self-heal one work item's stray state, then stop

USAGE
    pdlc continue WORK_ITEM

DESCRIPTION
    Corrects a work item found at a (Status, Gate State) combination that no
    pdlc command ever writes, but that has exactly one sane reading:

      - Approved on a non-terminal stage: no pdlc command ever leaves a gate
        there — Approved is reserved for the terminal stage — so it can only
        mean the stage was just approved. Advances to the next stage's
        Pending with a PDLC-APPROVED comment — unless the stage's evidence
        would make `pdlc post approve` refuse (no publication on record, a
        change request open since it, or no passing review of an
        Implementation or Testing publication); then it lands on the stage's
        own Approval Required with a plain comment naming what is missing, so
        the approval stops for the driver. At the completion boundary
        (Verification) it returns to Approval Required with a plain comment
        instead, never to Complete: completion runs its readiness checks only
        through `pdlc post complete`.
      - CI Pending on a stage that isn't CI-gated: that stage's own work
        never depends on CI, so its outcome is irrelevant. Advances straight
        to the stage's own result gate, ignoring red/green, with a plain
        comment recording the correction.
      - Review Required on a stage with no independent review policy
        (Verification): nothing dispatches a reviewer there, so it can only
        mean review was skipped. Lands where a clean verification run lands —
        CI Pending on a CI-gated stage, so the PR stack's CI is still checked
        before any human approval — with a plain comment.

    Refuses (exit 1) for every other state, including one `pdlc next` would
    happily route (Pending, Approval Required, Review Required, ...) —
    those aren't malformed, so there is nothing to heal; run `pdlc next`
    instead. `pdlc next` already applies this same correction inline before
    routing, so calling `pdlc continue` first is never required — it exists
    for a caller that has independently detected a stray state and wants to
    correct it without also triggering a routing decision.
"""

from __future__ import annotations

import json
import sys


from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import Lifecycle, State
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.workitem import (
    heal_item,
    item_gate,
    item_status,
    pipeline_for_item,
    resolve_item,
)


def continue_(issue: str) -> dict:
    item = resolve_item(issue)
    pipeline = pipeline_for_item(item)
    status = item_status(item)
    lifecycle = item.get("Lifecycle") or (Lifecycle.COMPLETED if status == pipeline.terminal_stage else Lifecycle.PLANNING)
    try:
        state = State.parse(status, item_gate(item), lifecycle)
    except ValueError as error:
        raise PdlcError(str(error)) from None

    healed = heal_item(item, str(issue), pipeline, state)
    if healed is None:
        raise PdlcError(f"{state.notation} is not a self-healable state; nothing to correct")
    return {"healed": True, "work_item": int(issue), "from": state.notation, "to": healed.notation}


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0
    if len(command_args) != 1:
        print("usage: pdlc continue WORK_ITEM", file=sys.stderr)
        return 1

    try:
        result = continue_(command_args[0])
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
