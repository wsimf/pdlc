#!/usr/bin/env python3
"""Records an independent reviewer's read-only verdict as PDLC-REVIEW with
script-owned Stage, Verdict, Bounce, and Loop metadata followed by Findings.
A reviewer may set Changes Required, Approval Required, or Decision Required —
never Approved.

    pdlc post review WORK_ITEM changes-required|approval-required|decision-required EVIDENCE_FILE|- [--attachment PATH [--attachment-description TEXT]]

`decision-required` is for a finding the owning skill cannot mechanically
reconcile — one that needs a product, architecture, UX, or scope call from the
driver. It halts the autonomous loop immediately (no reconciliation passes) and
posts the evidence through the backend's blocker channel under a PDLC-DECISION
marker. The evidence body must carry a `## Decision Required` section.

A clean `approval-required` review of the Implementation stage lands `CI Pending`,
not `Approval Required`: the reviewer judged the code while the shared PR's CI
was still in flight. This script then reconciles it immediately against the live
check state (advancing to `Approval Required` if CI is already green, dropping to
`Changes Required` with a PDLC-IMPLEMENTATION note if already red) and otherwise
leaves it at `CI Pending` for pdlc post ci / the loop to resolve when CI
finishes. Every other stage lands `Approval Required` as before — except a
clean Testing review on a record that has already been reworked within the churn
cap, which skips the human approval step (PDLC-AUTOAPPROVED) and lands on
Verification / Pending. See internal/churn_gate.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


from pdlc.internal.ci_gate import resolve_ci_gate  # type: ignore
from pdlc.internal.churn_gate import autoapprove_stage  # type: ignore
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number  # type: ignore
from pdlc.internal.workitem import is_stage_skipped, item_for_issue, item_gate, item_status, post_blocker, post_comment, set_gate, workflow_for_item  # type: ignore
from pdlc.domain.evidence import ReviewVerdict, compose_review  # type: ignore
from pdlc.domain.lifecycle import PdlcError, print_help, unmarked_evidence_source, wants_help  # type: ignore
from pdlc.domain.workflow import Event, Gate, Outcome

REVIEW_OUTCOMES = {
    "changes-required": Outcome.FINDINGS,
    "approval-required": Outcome.CLEAN,
    "decision-required": Outcome.DECISION,
}
REVIEW_VERDICTS = {
    "changes-required": ReviewVerdict.CHANGES_REQUIRED,
    "approval-required": ReviewVerdict.PASS,
    "decision-required": ReviewVerdict.DECISION_REQUIRED,
}

DECISION_HEADING = "## Decision Required"


def review(issue: str, outcome: str, evidence: str, attachment_inputs: list[dict]) -> dict:
    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)

    stage = item_status(record)
    if is_stage_skipped(record, stage):
        raise PdlcError("cannot review a stage declared in Skipped States")

    if outcome not in REVIEW_OUTCOMES:
        raise PdlcError(f"invalid review outcome: {outcome}")
    try:
        target = pipeline.next_state(state, Event.REVIEWED, REVIEW_OUTCOMES[outcome])
    except ValueError as error:
        raise PdlcError(str(error)) from None
    ci_pending = target.gate == Gate.CI_PENDING

    path, is_temporary = unmarked_evidence_source("evidence", evidence)
    try:
        body = path.read_text()
    finally:
        if is_temporary:
            path.unlink(missing_ok=True)
    if outcome == "decision-required" and DECISION_HEADING not in body:
        raise PdlcError(f"a decision-required review must include a '{DECISION_HEADING}' section")

    attachments = save_attachments(work_item_number(record), attachment_inputs)
    review_body = compose_review(stage, REVIEW_VERDICTS[outcome], f"## Findings\n\n{body.strip()}")
    post_comment(issue, review_body, "REVIEW")
    if outcome == "decision-required":
        post_blocker(issue, body, "DECISION")

    # A demonstrably-reworked Testing stage clears its approval gate with no
    # human step, landing straight on Verification / Pending. Implementation's
    # equivalent is handled downstream by the CI gate.
    landed = None
    if target.gate == Gate.APPROVAL_REQUIRED:
        landed = autoapprove_stage(issue, record, pipeline, target)

    if landed is None:
        set_gate(record["id"], target.gate.value)

    result = {"reviewed": True, "itemId": record["id"], "work_item": int(issue), "stage": stage, "gateState": target.gate.value, "attachments": attachments}

    if landed is not None:
        result["gateState"] = landed
        result["autoApproved"] = True
    elif ci_pending:
        ci = resolve_ci_gate(issue, record, pipeline, target)
        result["gateState"] = ci["gateState"]
        result["ci"] = ci

    return result


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
        print(
            "usage: pdlc post review WORK_ITEM changes-required|approval-required|decision-required EVIDENCE_FILE|-",
            file=sys.stderr,
        )
        return 1
    issue, outcome, evidence = args

    try:
        result = review(issue, outcome, evidence, attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
