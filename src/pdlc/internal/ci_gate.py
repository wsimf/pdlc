"""The `Implementation / CI Pending` gate.

A clean implementation review lands `CI Pending` rather than `Approval Required`:
the reviewer judged the code while the shared PR's CI was still in flight, and
the only thing left is the check outcome. This module reads that outcome from
the code host and reconciles the gate — green (or no checks tracked) advances to
`Approval Required`, red posts a `PDLC-IMPLEMENTATION` note and drops to
`Changes Required`. It is mechanical: it records an external fact and makes no
judgement, so the autonomous loop resolves it unattended.

On green, a record that has already been reworked within the churn cap skips the
human approval step entirely (see churn_gate) and lands on Testing / Pending.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pdlc.internal.churn_gate import autoapprove_stage
from pdlc.internal.pull_requests import record_pull_requests
from pdlc.internal.workitem import post_comment, set_gate
from pdlc.domain.workflow import Event, Outcome, Pipeline, State

# statusCheckRollup states that mean the run is settled and failed, still
# running, or settled and passed. Anything else (notably "NONE" — no checks
# configured) is treated as nothing to wait on.
_RED = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
_PENDING = {"PENDING", "EXPECTED", "IN_PROGRESS", "QUEUED", "WAITING", "REQUESTED"}


def ci_state(issue: str) -> tuple[str, list[dict]]:
    """One of "pending", "red", "green", "untracked", plus the pull requests it
    was read from. "untracked" means no registered PR, or none with CI
    configured — there is nothing to wait on, so the caller advances."""
    pull_requests = record_pull_requests(issue)
    if not pull_requests:
        return "untracked", []

    checks = [pr.get("checks") or "NONE" for pr in pull_requests]
    if any(state in _RED for state in checks):
        return "red", pull_requests
    if any(state in _PENDING for state in checks):
        return "pending", pull_requests
    # "NONE" (no checks configured on that PR) is neutral, not disqualifying: a
    # stack where every tracked PR is green and the rest have no CI is green.
    tracked = [state for state in checks if state != "NONE"]
    if tracked and all(state == "SUCCESS" for state in tracked):
        return "green", pull_requests
    return "untracked", pull_requests


def peek_ci_state(issue: str) -> str:
    """The CI state with no mutation — routing reads this to decide between
    backing off (pending) and recording the outcome."""
    return ci_state(issue)[0]


def resolve_ci_gate(issue: str, record: dict, pipeline: Pipeline, source: State) -> dict:
    """Reconcile an `Implementation / CI Pending` record against live CI.
    Caller has already confirmed the gate; this only reads the outcome and
    moves the gate."""
    state, pull_requests = ci_state(issue)

    if state == "pending":
        target = pipeline.next_state(source, Event.CI_RECONCILED, Outcome.CHECKS_PENDING)
        return {"state": "pending", "changed": False, "gateState": target.gate.value}

    if state == "red":
        failed = ", ".join(
            f"#{pr['number']} ({pr.get('checks')})"
            for pr in pull_requests
            if (pr.get("checks") or "") in _RED
        )
        body = (
            "CI checks failed on the implementation pull request(s) after the implementation "
            f"review was approved: {failed}.\n\n"
            "Implementation returns to Changes Required. pdlc-implement inspects the failing "
            "checks, fixes them on the implementation pull request(s), and re-publishes for review."
        )
        descriptor, name = tempfile.mkstemp()
        with os.fdopen(descriptor, "w") as handle:
            handle.write(body)
        try:
            post_comment(str(issue), name, "IMPLEMENTATION")
        finally:
            Path(name).unlink(missing_ok=True)
        target = pipeline.next_state(source, Event.CI_RECONCILED, Outcome.CHECKS_FAILED)
        set_gate(record["id"], target.gate.value)
        return {"state": "red", "changed": True, "gateState": target.gate.value, "failed": failed}

    # A demonstrably-reworked record clears the Implementation approval gate
    # with no human step, landing straight on the next stage's Pending.
    target = pipeline.next_state(source, Event.CI_RECONCILED, Outcome.CHECKS_PASSED)
    landed = autoapprove_stage(issue, record, pipeline, target)
    if landed:
        return {"state": state, "changed": True, "gateState": landed, "autoApproved": True}

    set_gate(record["id"], target.gate.value)
    return {"state": state, "changed": True, "gateState": target.gate.value}
