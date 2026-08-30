#!/usr/bin/env python3
"""Records an independent reviewer's read-only verdict. A reviewer may set
Changes Required, Approval Required, or Decision Required — never Approved.

    pdlc-post-review.py WORK_ITEM changes-required|approval-required|decision-required EVIDENCE_FILE|- [--attachment PATH [--attachment-description TEXT]]

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
leaves it at `CI Pending` for pdlc-post-ci.py / the loop to resolve when CI
finishes. Every other stage lands `Approval Required` as before — except a
clean Testing review on a record that has already been reworked within the churn
cap, which skips the human approval step (PDLC-AUTOAPPROVED) and lands on
Verification / Pending. See lib/churn_gate.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


from pdlc.internal.ci_gate import resolve_ci_gate  # type: ignore
from pdlc.internal.churn_gate import autoapprove_stage  # type: ignore
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number  # type: ignore
from pdlc.internal.workitem import is_stage_skipped, item_for_issue, item_gate, item_status, post_blocker, post_comment, set_gate  # type: ignore
from pdlc.domain.lifecycle import PdlcError, evidence_source, marker_for_stage, print_help, wants_help  # type: ignore

OUTCOME_GATES = {
    "changes-required": "Changes Required",
    "approval-required": "Approval Required",
    "decision-required": "Decision Required",
}

DECISION_HEADING = "## Decision Required"


def review(issue: str, outcome: str, evidence: str, attachment_inputs: list[dict]) -> dict:
    record = item_for_issue(issue)
    if item_gate(record) != "Review Required":
        raise PdlcError("review requires Gate State = Review Required")

    stage = item_status(record)
    if is_stage_skipped(record, stage):
        raise PdlcError("cannot review a stage declared in Skipped States")

    if outcome not in OUTCOME_GATES:
        raise PdlcError(f"invalid review outcome: {outcome}")
    gate = OUTCOME_GATES[outcome]

    # A clean Implementation review does not wait for CI: it lands CI Pending,
    # then this script reconciles it against the live check state below.
    ci_pending = outcome == "approval-required" and stage == "Implementation"
    if ci_pending:
        gate = "CI Pending"

    if outcome == "decision-required":
        path, is_temporary = evidence_source("evidence", evidence)
        try:
            body = path.read_text()
        finally:
            if is_temporary:
                path.unlink(missing_ok=True)
        if DECISION_HEADING not in body:
            raise PdlcError(f"a decision-required review must include a '{DECISION_HEADING}' section")
        attachments = save_attachments(work_item_number(record), attachment_inputs)
        post_blocker(issue, body, "DECISION")
    else:
        attachments = save_attachments(work_item_number(record), attachment_inputs)
        post_comment(issue, evidence, marker_for_stage(stage))

    # A demonstrably-reworked Testing stage clears its approval gate with no
    # human step, landing straight on Verification / Pending. Implementation's
    # equivalent is handled downstream by the CI gate.
    landed = None
    if outcome == "approval-required" and stage == "Testing":
        landed = autoapprove_stage(issue, record, "Testing")

    if landed is None:
        set_gate(record["id"], gate)

    result = {"reviewed": True, "itemId": record["id"], "work_item": int(issue), "stage": stage, "gateState": gate, "attachments": attachments}

    if landed is not None:
        result["gateState"] = landed
        result["autoApproved"] = True
    elif ci_pending:
        ci = resolve_ci_gate(issue, record)
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
            "usage: pdlc-post-review.py WORK_ITEM changes-required|approval-required|decision-required EVIDENCE_FILE|-",
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
