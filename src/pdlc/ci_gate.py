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

from pdlc.churn_gate import autoapprove_stage
from pdlc.code_host import get_code_host
from pdlc.workitem import post_comment, set_gate

# statusCheckRollup states that mean the run is settled and failed, still
# running, or settled and passed. Anything else (notably "NONE" — no checks
# configured) is treated as nothing to wait on.
_RED = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
_PENDING = {"PENDING", "EXPECTED", "IN_PROGRESS", "QUEUED", "WAITING", "REQUESTED"}


def _relevant_pull_requests(issue: str) -> list[dict]:
    pull_requests = get_code_host().pull_requests(str(issue))
    closing = [pr for pr in pull_requests if pr.get("relation") == "closes"]
    return closing or pull_requests


def ci_state(issue: str) -> tuple[str, list[dict]]:
    """One of "pending", "red", "green", "untracked", plus the pull requests it
    was read from. "untracked" means no linked PR, or none with CI configured —
    there is nothing to wait on, so the caller advances."""
    pull_requests = _relevant_pull_requests(issue)
    if not pull_requests:
        return "untracked", []

    checks = [pr.get("checks") or "NONE" for pr in pull_requests]
    if any(state in _RED for state in checks):
        return "red", pull_requests
    if any(state in _PENDING for state in checks):
        return "pending", pull_requests
    if all(state == "SUCCESS" for state in checks):
        return "green", pull_requests
    return "untracked", pull_requests


def peek_ci_state(issue: str) -> str:
    """The CI state with no mutation — routing reads this to decide between
    backing off (pending) and recording the outcome."""
    return ci_state(issue)[0]


def resolve_ci_gate(issue: str, record: dict) -> dict:
    """Reconcile an `Implementation / CI Pending` record against live CI.
    Caller has already confirmed the gate; this only reads the outcome and
    moves the gate."""
    state, pull_requests = ci_state(issue)

    if state == "pending":
        return {"state": "pending", "changed": False, "gateState": "CI Pending"}

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
            "checks, fixes them on the shared PR, and re-publishes for review."
        )
        descriptor, name = tempfile.mkstemp()
        with os.fdopen(descriptor, "w") as handle:
            handle.write(body)
        try:
            post_comment(str(issue), name, "IMPLEMENTATION")
        finally:
            Path(name).unlink(missing_ok=True)
        set_gate(record["id"], "Changes Required")
        return {"state": "red", "changed": True, "gateState": "Changes Required", "failed": failed}

    # A demonstrably-reworked record clears the Implementation approval gate
    # with no human step, landing straight on the next stage's Pending.
    landed = autoapprove_stage(issue, record, "Implementation")
    if landed:
        return {"state": state, "changed": True, "gateState": landed, "autoApproved": True}

    set_gate(record["id"], "Approval Required")
    return {"state": state, "changed": True, "gateState": "Approval Required"}
