#!/usr/bin/env python3
"""NAME
    pdlc post verify - post verification results and move the Verification gate

USAGE
    pdlc post verify WORK_ITEM REPORT_FILE|- --recommendation TEXT [--attachment PATH [--attachment-description TEXT]]
        [--fixed FIXED_FILE|-] [--deferred DEFERRED_FILE|-]
        [--decision DECISION_FILE|-] [--bounce STAGE]

FLAGS
    --recommendation TEXT                 required; "Approval Required" | "Changes Required" | "Decision Required"
    --fixed FIXED_FILE|-                  one "description | commit" pair per line
    --deferred DEFERRED_FILE|-            one plain reason per line
    --decision DECISION_FILE|-            required with a Decision Required recommendation
    --bounce STAGE                        with Changes Required, return an upstream stage to Stale instead
    --attachment PATH (repeatable)        attach a local file's contents to the verification comment
    --attachment-description TEXT         description for the --attachment immediately before it

DESCRIPTION
    Posts a durable "Verification Run Results" comment on a PDLC parent work item,
    stamped with the current UTC time and a structured REVIEW marker, files any
    deferred findings into the parent's Open Questions section, and moves the
    Verification gate to match the run's recommendation. Every run adds a new
    comment rather than editing a prior one, so the work item's comment history is
    the full, permanent verification log.

The caller hands over raw findings only — a plain description, and for fixed
items the commit it was re-verified against — and makes no formatting
decisions: this script owns the Findings section (including its "None" empty
case and the `(Verified @ ...)` marker on each fixed item), the Open
Questions deferral lines (the `Deferred — ` marker), and the Recommendation
line. Deferred findings are filed into Open Questions only — never echoed
into the comment itself; pdlc inspect verify is how a later pass reads
both back, and owns parsing these same markers on the way in.

REPORT_FILE holds only the Claims Audit, User Journeys, UX, and Cumulative Review
sections — Findings and Recommendation are assembled here. On an
`Approval Required` run the assembled comment must satisfy the strict
`evidence.parse_verification_report` schema (all four sections non-empty,
every Claims Audit / User Journeys row carrying its `(Verified @ <commit>)`
anchor) that verify inspection and completion read it back through; a
malformed clean run is refused before anything is posted. DEFERRED_FILE is
one plain reason per line. FIXED_FILE is one `description | commit` pair per
line — the commit the fix was re-verified against, not embedded prose.
Omit either file, or leave it empty, when there's nothing to report for it.

--recommendation is one of "Approval Required", "Changes Required", or
"Decision Required", and sets the gate to that value on a successful post:

  - Approval Required — clean run; the driver approves, then pdlc post complete.
  - Changes Required  — a finding the skill can reconcile itself; the loop
                        routes straight back to pdlc-verify. With --bounce STAGE
                        the run instead returns that upstream stage to Stale
                        (recorded by the review's Bounce and Loop fields), so
                        the Implementation -> Testing -> Verification loop keeps
                        moving with no driver step. The verifier chooses the
                        target stage.
  - Decision Required — a finding that needs a product, architecture, UX,
                        safety, or scope call only the driver can make.
                        Requires --decision, a file carrying one or more
                        `## Decision Required` blocks; it is posted through
                        the backend's blocker channel under a PDLC-DECISION
                        marker, the autonomous loop halts on it, and the
                        driver clears it with pdlc post decision.

The gate is only moved when Status is Verification and the current gate is
Pending, Changes Required, or Stale — a run against an already-approved or
malformed record is refused.

Given a REPORT_FILE with Claims Audit / User Journeys / UX / Cumulative Review
sections, `--fixed` with one line
`Route line snapped to wrong profile on regen | b2c3d4e`, and `--deferred`
with one line `Elevation gain rounding drifts by 2m, accepted because it's
within tolerance`, the posted comment body is:

    PDLC-REVIEW

    ---
    stage: Verification
    verdict: Pass
    bounce: null
    loop: null
    ---

    ## Verification Run Results
    Run at 2026-08-24 09:14 UTC

    ### Claims Audit

    - WORK-142-TASK-007 — Confirmed: RouteShapeAnimator matches Result; C-2 holds (Verified @ a1b2c3d)

    ### User Journeys

    - UJ-3 — Accepted: offline retry confirmed in the running app (Verified @ a1b2c3d)

    ### UX

    - Reviewed — no critical findings (Verified @ a1b2c3d)

    ### Cumulative Review

    - Clean — no findings (Verified @ a1b2c3d)

    ### Findings

    - Route line snapped to wrong profile on regen (Verified @ b2c3d4e)

    Recommendation: Approval Required

and the parent work item's Open Questions section gets one new bullet appended:
`Deferred — Elevation gain rounding drifts by 2m, accepted because it's
within tolerance`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


from pdlc.internal.workitem import (
    append_to_section,
    item_for_issue,
    post_blocker,
    post_comment,
    set_gate,
    workflow_for_item,
)
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number
from pdlc.internal.ci_gate import resolve_ci_gate
from pdlc.internal.invalidation import bounce_stage
from pdlc.domain.evidence import ReviewVerdict, compose_review, parse_verification_report
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import is_stdin, resolve_text, print_help, wants_help
from pdlc.domain.workflow import Event, Gate, Outcome

RECOMMENDATIONS = ("Approval Required", "Changes Required", "Decision Required")
DECISION_HEADING = "## Decision Required"
VERIFICATION_OUTCOMES = {
    "Approval Required": Outcome.CLEAN,
    "Changes Required": Outcome.FINDINGS,
    "Decision Required": Outcome.DECISION,
}


def _lines_from(source: str | None) -> list[str]:
    if not source:
        return []
    return [line.strip() for line in resolve_text(source, label="findings").splitlines() if line.strip()]


def _fixed_bullet(line: str) -> str:
    description, sep, commit = line.partition("|")
    if not sep:
        raise PdlcError(f"--fixed line missing '| commit': {line!r}")
    description = description.strip()
    commit = commit.strip()
    if not description or not commit:
        raise PdlcError(f"--fixed line missing description or commit: {line!r}")
    return f"- {description} (Verified @ {commit})"


def post_verify(
    issue: str,
    report: str,
    recommendation: str,
    fixed: str | None,
    deferred: str | None,
    decision: str | None,
    bounce: str | None = None,
    attachment_inputs: list[dict] | None = None,
) -> dict:
    if recommendation not in RECOMMENDATIONS:
        raise PdlcError(f"--recommendation must be one of: {', '.join(RECOMMENDATIONS)}")

    is_decision = recommendation == "Decision Required"
    if is_decision and not decision:
        raise PdlcError("--decision is required when --recommendation is 'Decision Required'")
    if decision and not is_decision:
        raise PdlcError("--decision is only valid with --recommendation 'Decision Required'")
    if bounce and recommendation != "Changes Required":
        raise PdlcError("--bounce is only valid with --recommendation 'Changes Required'")

    stdin_sources = [
        name
        for name, source in (("report", report), ("--fixed", fixed), ("--deferred", deferred), ("--decision", decision))
        if source is not None and is_stdin(source)
    ]
    if len(stdin_sources) > 1:
        raise PdlcError(f"stdin can supply only one input, not: {', '.join(stdin_sources)}")

    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)
    try:
        target = pipeline.next_state(state, Event.VERIFIED, VERIFICATION_OUTCOMES[recommendation])
        if bounce:
            pipeline.next_state(target, Event.BOUNCED, requested_target=bounce)
    except ValueError as error:
        raise PdlcError(str(error)) from None

    report_text = resolve_text(report, label="report").strip()

    decision_body = resolve_text(decision, label="--decision") if is_decision else ""
    if is_decision and DECISION_HEADING not in decision_body:
        raise PdlcError(f"a decision-required verification must include a '{DECISION_HEADING}' section")

    fixed_items = _lines_from(fixed)
    deferred_items = _lines_from(deferred)

    findings_block = "\n".join(_fixed_bullet(line) for line in fixed_items) if fixed_items else "None"

    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = [
        f"## Verification Run Results\nRun at {run_at}",
        report_text,
        f"### Findings\n\n{findings_block}",
        f"Recommendation: {recommendation}",
    ]

    comment_body = "\n\n".join(sections) + "\n"

    # A clean run's evidence must satisfy the one strict parser every
    # downstream gate (verify inspection, completion) reads it back through —
    # non-clean runs are not asserting the record is done, so they only need
    # a non-empty report.
    if recommendation == "Approval Required":
        try:
            parse_verification_report(comment_body)
        except PdlcError as error:
            raise PdlcError(f"clean verification evidence is not valid: {error}") from None

    policy = pipeline.rework_policy
    if bounce and policy is None:
        raise PdlcError("this pipeline has no rework loop")
    verdict = {
        "Approval Required": ReviewVerdict.PASS,
        "Changes Required": ReviewVerdict.CHANGES_REQUIRED,
        "Decision Required": ReviewVerdict.DECISION_REQUIRED,
    }[recommendation]
    review_body = compose_review(
        "Verification",
        verdict,
        comment_body,
        bounce=bounce,
        loop=policy.name if bounce and policy is not None else None,
    )

    attachments = save_attachments(work_item_number(record), attachment_inputs or [])
    post_comment(issue, review_body, "REVIEW")

    append_to_section(issue, "Open Questions", [f"Deferred — {line}" for line in deferred_items])

    if is_decision:
        post_blocker(issue, decision_body, "DECISION")

    # --bounce routes a Changes Required run straight back to an upstream stage.
    # Its provenance and loop identity live in the PDLC-REVIEW comment above;
    # PDLC-INVALIDATED remains reserved for explicit driver invalidation.
    if bounce:
        bounced = bounce_stage(
            record,
            pipeline,
            target,
            bounce,
        )
        return {"posted": True, "workItem": int(issue), "itemId": record["id"],
                "gateState": bounced.gate.value, "bouncedTo": bounced.stage, "attachments": attachments}

    set_gate(record["id"], target.gate.value)
    result = {"posted": True, "workItem": int(issue), "itemId": record["id"], "gateState": target.gate.value, "attachments": attachments}

    # A clean run is CI-gated, same as Implementation/Testing: it parks at CI
    # Pending rather than Approval Required. Resolving it here immediately
    # (rather than requiring a separate `pdlc post ci` call) matches those
    # stages' own review commands — if checks already settled by verify time
    # this advances straight through; if not, it stays parked until a driver
    # or the autonomous loop runs `pdlc post ci`.
    if target.gate == Gate.CI_PENDING:
        ci = resolve_ci_gate(issue, record, pipeline, target)
        result["gateState"] = ci["gateState"]
        result["ci"] = ci

    return result


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw_args = command_args
    if wants_help(raw_args):
        print_help(__doc__)
        return 0

    try:
        script_args, attachment_inputs = parse_attachment_arguments(raw_args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="Post a PDLC verification report")
    parser.add_argument("work_item")
    parser.add_argument("report", help="Claims Audit / User Journeys / UX / Cumulative Review sections — a file path, or - for stdin")
    parser.add_argument("--recommendation", required=True, choices=list(RECOMMENDATIONS))
    parser.add_argument("--fixed", help="File of fixed findings, one per line, or - for stdin")
    parser.add_argument("--deferred", help="File of deferred findings, one per line, or - for stdin")
    parser.add_argument("--decision", help="File of '## Decision Required' blocks, or - for stdin (Decision Required only)")
    parser.add_argument(
        "--bounce",
        metavar="STAGE",
        help="Return this stage to Stale instead of parking at Changes Required (Changes Required only)",
    )
    args = parser.parse_args(script_args)

    try:
        result = post_verify(
            args.work_item, args.report, args.recommendation, args.fixed, args.deferred, args.decision, args.bounce,
            attachment_inputs,
        )
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
