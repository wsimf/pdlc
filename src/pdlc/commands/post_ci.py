#!/usr/bin/env python3
"""NAME
    pdlc post ci - resolve CI Pending against live check state

USAGE
    pdlc post ci WORK_ITEM

DESCRIPTION
    Resolves a CI-gated stage's record (Implementation, Testing, Verification)
    parked at `CI Pending` against the live check state of its pull request(s).

  - checks still running          -> no change; reports "still running"
  - checks green / none tracked   -> Stage / Approval Required
  - checks red                    -> posts a note under the stage's own
                                     marker and Stage / Changes Required

Mechanical: it records an external fact, makes no judgement, and carries no
identity check. The autonomous loop runs it once CI finishes; a driver may run
it directly when resuming a CI-Pending record. It refuses any other gate.

The command prints Markdown instructions: retry this command while CI is
pending, inspect the work item after a pass, and inspect it for the next
actions after a failure.
"""

from __future__ import annotations

import sys


from pdlc.internal.ci_gate import resolve_ci_gate
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import decision_required_message
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.workitem import item_for_issue, item_gate, workflow_for_item


def post_ci(issue: str) -> dict:
    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)
    if item_gate(record) == "Decision Required":
        raise PdlcError(decision_required_message(state.stage))
    if item_gate(record) != "CI Pending":
        raise PdlcError(f"pdlc post ci requires Gate State = CI Pending, not {item_gate(record) or 'unset'}")

    result = resolve_ci_gate(issue, record, pipeline, state)
    return {"workItem": int(issue), "itemId": record["id"], "stage": state.stage, **result}


def render_result(issue: str, result: dict) -> str:
    """Render the mechanical CI outcome as instructions for the next agent."""
    state = result["state"]
    stage = result["stage"]
    if state == "pending":
        return (
            "## CI Pending\n\n"
            f"CI is still pending for the {stage} pull request(s).\n\n"
            f"Call `pdlc post ci {issue}` again after some time."
        )
    if state == "red":
        failed = result.get("failed", "the registered pull request checks")
        return (
            "## CI Failed\n\n"
            f"CI failed for the {stage} pull request(s).\n\n"
            f"Failed checks: {failed}.\n\n"
            f"Run `pdlc inspect {issue}` for the next actions."
        )
    if state == "untracked":
        return (
            "## CI Not Tracked\n\n"
            f"No CI checks are configured for the {stage} pull request(s).\n\n"
            f"Run `pdlc inspect {issue}` to get the next action."
        )
    return (
        "## CI Passed\n\n"
        f"CI passed for the {stage} pull request(s).\n\n"
        f"Run `pdlc inspect {issue}` to get the next action."
    )


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    args = command_args
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

    print(render_result(args[0], result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
