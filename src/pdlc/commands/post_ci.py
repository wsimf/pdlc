#!/usr/bin/env python3
"""NAME
    pdlc post ci - resolve CI Pending against live check state

USAGE
    pdlc post ci WORK_ITEM [--wait]

DESCRIPTION
    Resolves a CI-gated stage's record (Implementation, Testing, Verification)
    parked at `CI Pending` against the live check state of its pull request(s).

  - checks still running          -> no change; reports "still running", or waits when --wait is set
  - checks green / none tracked   -> Stage / Approval Required
  - checks red                    -> posts a PDLC-REVIEW note opening with
                                     `CI failed stage: <stage>` and naming the
                                     failed PRs, and Stage / Changes Required
  - no registered PR on Implementation or Testing
                                  -> no change; exits 1

"None tracked" means the registered PRs have no checks configured, or — on
Verification, which ships no PR of its own — that none is registered.
Implementation and Testing publish through their pull requests, so with none
registered there is no CI to have passed: the command refuses, leaves the
record at `CI Pending`, and names the stage; register its pull requests
(`pdlc post attach-pr` for a delivery task's PR) and run it again.

Mechanical: it records an external fact, makes no judgement, and carries no
identity check. With --wait, it polls the registered PR stack with exponential
backoff capped at two minutes, then reconciles the gate as soon as CI settles.
It times out after one hour, leaving the record unchanged. A driver may omit
--wait for a one-shot check. It refuses any other gate.

The command prints Markdown instructions: retry this command while CI is
pending, inspect the work item after a pass, and inspect it for the next
actions after a failure.

FLAGS
    --wait    action="store_true"; poll pending checks with capped exponential backoff for up to one hour
"""

from __future__ import annotations

import sys
import time


from pdlc.internal.ci_gate import resolve_ci_gate
from pdlc.domain.lifecycle import PdlcError, TransientError
from pdlc.hosts.lib import process
from pdlc.domain.workflow import decision_required_message
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.workitem import item_for_issue, item_gate, workflow_for_item
from pdlc.internal.failure import Recovery, report_failure, set_recovery


CI_WAIT_INITIAL_DELAY_SECONDS = 30
CI_WAIT_MAX_DELAY_SECONDS = 120
CI_WAIT_TIMEOUT_SECONDS = 60 * 60


def post_ci(issue: str) -> dict:
    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)
    if item_gate(record) == "Decision Required":
        raise PdlcError(decision_required_message(state.stage))
    if item_gate(record) != "CI Pending":
        raise PdlcError(f"pdlc post ci requires Gate State = CI Pending, not {item_gate(record) or 'unset'}")

    result = resolve_ci_gate(issue, record, pipeline, state)
    if result["state"] == "missing":
        raise PdlcError(
            f"{state.stage} has no registered pull request, so no CI was checked; the record stays at CI Pending. "
            "Register the stage's pull requests (pdlc post attach-pr DELIVERY_TASK PR_NUMBER) and run this again"
        )
    return {"workItem": int(issue), "itemId": record["id"], "stage": state.stage, **result}


def wait_for_ci(issue: str) -> dict:
    """Poll one CI-pending stage until its aggregate PR state settles."""
    deadline = time.monotonic() + CI_WAIT_TIMEOUT_SECONDS
    delay = CI_WAIT_INITIAL_DELAY_SECONDS
    stage = "CI-gated"

    while True:
        transient: TransientError | None = None
        try:
            result = post_ci(issue)
        except TransientError as error:
            # Nothing written yet means CI simply could not be read this
            # time: keep polling. After a write, report it for recovery.
            if process.write_started():
                raise
            print(f"pdlc: transient: {error}; treating CI as still pending", file=sys.stderr)
            transient = error
            result = {"state": "pending", "stage": stage}
        stage = result["stage"]
        if result["state"] != "pending":
            return result

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if transient is not None:
                raise transient
            raise PdlcError(
                f"CI is still pending for the {result['stage']} pull request(s) after one hour; "
                "the record stays at CI Pending"
            )

        wait_seconds = min(delay, remaining)
        print(
            f"CI is still pending for {result['stage']}; checking again in {wait_seconds:g}s…",
            file=sys.stderr,
        )
        time.sleep(wait_seconds)
        delay = min(delay * 2, CI_WAIT_MAX_DELAY_SECONDS)


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
    wait = "--wait" in args
    if wait:
        args.remove("--wait")
    if len(args) != 1 or any(arg.startswith("-") for arg in args):
        print("usage: pdlc post ci WORK_ITEM [--wait]", file=sys.stderr)
        return 1

    try:
        set_recovery(Recovery(
            check=f"pdlc inspect {args[0]}",
            landed="the gate has left CI Pending",
            note="A re-run after a CI-failed PDLC-REVIEW landed posts a second one; mention it in your report.",
        ))
        result = wait_for_ci(args[0]) if wait else post_ci(args[0])
    except PdlcError as error:
        return report_failure(error)

    print(render_result(args[0], result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
