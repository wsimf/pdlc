"""The `CI Pending` gate for a CI-gated stage (Implementation, Testing, Verification).

A clean review of a CI-gated stage lands `CI Pending` rather than `Approval Required`:
the reviewer judged the work while the registered PR stack's CI was still in flight, and
the only thing left is the check outcome. This module reads that outcome from
the code host and reconciles the gate — green (or no checks tracked) advances to
`Approval Required`, red posts a `PDLC-REVIEW` note with the failed checks and
drops to `Changes Required`. It is mechanical: it records an external fact and
makes no judgement, so the autonomous loop resolves it unattended.

On green, a record that has already been reworked within the churn cap skips the
human approval step entirely (see churn_gate) and lands on the next stage's Pending.

A stage that publishes through pull requests (Implementation, Testing) with none
registered reports "missing" and holds `CI Pending`: no stack means no CI was
checked, not that there is nothing to wait on. Only a stage that ships no PR of its
own (Verification) passes with none registered.
"""

from __future__ import annotations

from pdlc.internal.churn_gate import autoapprove_stage
from pdlc.internal.pull_requests import record_pull_requests
from pdlc.internal.workitem import post_comment, set_gate
from pdlc.domain.workflow import Event, Outcome, Pipeline, State

# statusCheckRollup states that mean the run is settled and failed, still
# running, or settled and passed. Anything else (notably "NONE" — no checks
# configured) is treated as nothing to wait on.
_RED = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
_PENDING = {"PENDING", "EXPECTED", "IN_PROGRESS", "QUEUED", "WAITING", "REQUESTED"}


def check_state(checks: str | None) -> str:
    """One pull request's rollup as "red", "pending", "green", or "none" (no
    checks configured). The single reading of the host's rollup vocabulary,
    shared by the CI gate and by `pdlc inspect implement`'s per-task view."""
    state = checks or "NONE"
    if state in _RED:
        return "red"
    if state in _PENDING:
        return "pending"
    if state == "SUCCESS":
        return "green"
    return "none"


def ci_state(issue: str) -> tuple[str, list[dict]]:
    """One of "pending", "red", "green", "untracked", plus the pull requests it
    was read from. "untracked" means no registered PR, or none with CI
    configured — there is nothing to wait on, so the caller advances (see
    `resolve_ci_gate` for a stage that must have registered PRs)."""
    pull_requests = record_pull_requests(issue)
    if not pull_requests:
        return "untracked", []

    states = [check_state(pr.get("checks")) for pr in pull_requests]
    if "red" in states:
        return "red", pull_requests
    if "pending" in states:
        return "pending", pull_requests
    # "none" (no checks configured on that PR) is neutral, not disqualifying: a
    # stack where every tracked PR is green and the rest have no CI is green.
    tracked = [state for state in states if state != "none"]
    if tracked and all(state == "green" for state in tracked):
        return "green", pull_requests
    return "untracked", pull_requests


def peek_ci_state(issue: str) -> str:
    """The CI state with no mutation — routing reads this to decide between
    backing off (pending) and recording the outcome."""
    return ci_state(issue)[0]


def resolve_ci_gate(issue: str, record: dict, pipeline: Pipeline, source: State) -> dict:
    """Reconcile a CI-gated stage's `CI Pending` record against live CI.
    Caller has already confirmed the gate; this only reads the outcome and
    moves the gate. "pending" and "missing" (a pull-request stage with none
    registered) leave it at `CI Pending`."""
    stage = pipeline.stage(source.stage)
    state, pull_requests = ci_state(issue)
    if not pull_requests and stage.publishes_pull_requests:
        state = "missing"

    if state in ("pending", "missing"):
        target = pipeline.next_state(source, Event.CI_RECONCILED, Outcome.CHECKS_PENDING)
        return {"state": state, "changed": False, "gateState": target.gate.value}

    if state == "red":
        failed = ", ".join(
            f"#{pr['number']} ({pr.get('checks')})"
            for pr in pull_requests
            if (pr.get("checks") or "") in _RED
        )
        # The `CI failed stage:` line attributes this change request to its
        # stage for `pdlc inspect changes`; the note carries no review
        # metadata, so Verification evidence readers keep ignoring it.
        body = (
            f"CI failed stage: {stage.name}\n\n"
            f"CI check has failed on the {stage.name.lower()} pull request(s) after the "
            f"{stage.name.lower()} review was approved.\n\n"
            f"Failed checks: {failed}.\n\n"
            f"{stage.name} returns to Changes Required. Inspect the work item for the "
            "next actions and investigate the failed checks before re-publishing for review."
        )
        post_comment(str(issue), body, "REVIEW")
        target = pipeline.next_state(source, Event.CI_RECONCILED, Outcome.CHECKS_FAILED)
        set_gate(record["id"], target.gate.value)
        return {"state": "red", "changed": True, "gateState": target.gate.value, "failed": failed}

    # A demonstrably-reworked record clears the stage's approval gate
    # with no human step, landing straight on the next stage's Pending.
    target = pipeline.next_state(source, Event.CI_RECONCILED, Outcome.CHECKS_PASSED)
    landed = autoapprove_stage(issue, record, pipeline, target)
    if landed:
        return {"state": state, "changed": True, "gateState": landed, "autoApproved": True}

    set_gate(record["id"], target.gate.value)
    return {"state": state, "changed": True, "gateState": target.gate.value}
