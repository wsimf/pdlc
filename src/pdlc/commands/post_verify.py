#!/usr/bin/env python3
"""NAME
    pdlc post verify - post a verification report and move the Verification gate

USAGE
    pdlc post verify WORK_ITEM REPORT_FILE|text:JSON|- [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --attachment PATH (repeatable)      attach a local file's contents to the verification comment
    --attachment-description TEXT       description for the --attachment immediately before it

DESCRIPTION
    Posts a durable "Verification Run Results" comment on a PDLC parent work
    item from a filled-in verification report, records every finding's status,
    and moves the Verification gate to the outcome the report supports. Every
    run adds a new comment rather than editing a prior one, so the work item's
    comment history is the full, permanent verification log.

REPORT_FILE is the `pdlc.verify/1` JSON skeleton `pdlc inspect verify` wrote,
with its blanks filled in. The verifier supplies results, notes, finding
statuses, and new findings only. This command owns everything else: it stamps
the commit the report was checked at (HEAD), numbers new findings `F-<n>`,
derives the recommendation, and renders the comment. Fields the skeleton
carries for context (`title`, `reuse`, `author`, `excerpt`, a finding's
`about`/`text`) are ignored on input.

    {
      "schema": "pdlc.verify/1",
      "claims": [
        {"task": "TASK-007", "result": "confirmed", "note": "RouteSyncClient retries 503 with backoff"}
      ],
      "journeys": [
        {"journey": "UJ-3", "result": "accepted", "note": "offline retry confirmed in the running app"}
      ],
      "ux": {"result": "clean", "note": "no material findings"},
      "cumulativeReview": {"result": "findings", "scope": "master..feature/142-top", "note": "one low finding"},
      "openComments": [
        {"url": "https://github.com/acme/app/pull/57#discussion_r1", "action": "finding", "note": ""}
      ],
      "findings": [
        {"id": "F-1", "status": "fixed", "note": "503 now retried; covered by test503Backoff"}
      ],
      "newFindings": [
        {"about": "cumulative", "text": "Backoff jitter constant duplicated in two files",
         "source": "cumulative review", "status": "deferred", "note": "driver accepted: cosmetic"},
        {"about": "TASK-007", "text": "503s are not retried",
         "source": "https://github.com/acme/app/pull/57#discussion_r1", "status": "deferred",
         "note": "driver accepted for this release"}
      ],
      "bounce": null
    }

Results:

  - claims[].result — confirmed | failed | not_run; one row per closed delivery task.
  - journeys[].result — accepted | failed | not_run; one row per UJ journey in the
    parent's UI section. `journeys` is null when no delivery task is UI.
  - ux.result — clean | findings | not_run, or not_applicable when no task is UI.
  - cumulativeReview.result — clean | findings | not_run.
  - openComments[].action — finding (a newFindings entry has the comment URL as
    its source) | no_action (the note says why). Every still-unresolved review
    comment on the PR stack needs one.

Findings:

  - findings[] updates a finding already on the record by id: status open |
    fixed | deferred | decision. A finding left out keeps its status, except
    one previously sent to the driver as a decision, which must be given its
    outcome.
  - newFindings[] raises a finding: about (a task id, journey id, ux,
    cumulative, or general), text, optional source, status open | deferred |
    decision.
  - deferred needs a note with the driver's reason, and is appended to the
    parent's Open Questions as `Deferred — F-<n>: <text> (<note>)`.
  - decision needs a `decision` object: question, options (two or more),
    recommendation, blocks, whyNotMechanical. It is posted as a
    `## Decision Required` block through the backend's blocker channel under a
    PDLC-DECISION marker; the driver clears it with pdlc post decision.
  - A failed / findings row needs an open, deferred, or decision finding about it.

The recommendation is derived, never supplied, and sets the gate:

  - Decision Required — any finding is at decision. The autonomous loop halts.
  - Changes Required  — any finding is open, any row is not_run, or a failed row
                        has a finding that is not deferred. The loop routes
                        straight back to pdlc-verify. With "bounce": "STAGE" the
                        run instead returns that upstream stage to Stale
                        (recorded by the review's Bounce and Loop fields), so
                        the Implementation -> Testing -> Verification loop keeps
                        moving with no driver step. The verifier chooses the
                        target stage.
  - Approval Required — everything else: a clean run. The driver approves, then
                        pdlc post complete.

Every problem in the report is refused together, before anything is posted.
The command also refuses while tracked files differ from HEAD (HEAD would not
be what was checked), or while HEAD does not include every open task PR's head
commit — check out the top of the task stack, restacked, first.

The gate is only moved when Status is Verification and the current gate is
Pending, Changes Required, or Stale — a run against an already-approved or
malformed record is refused.

For the report above, checked at HEAD c47d0ae…, the posted comment body is:

    PDLC-REVIEW

    ---
    stage: Verification
    verdict: Pass
    bounce: null
    loop: null
    ---

    ## Verification Run Results
    Run at 2026-09-16 10:42 UTC · HEAD c47d0ae… · Approval Required

    ### Claims Audit

    - TASK-007 · confirmed — RouteSyncClient retries 503 with backoff

    ### User Journeys

    - UJ-3 · accepted — offline retry confirmed in the running app

    ### UX

    - ux · clean — no material findings

    ### Cumulative Review

    - cumulative · findings — master..feature/142-top; one low finding

    ### Open Comments

    - https://github.com/acme/app/pull/57#discussion_r1 · finding

    ### Findings

    - F-1 · fixed — 503 now retried; covered by test503Backoff
    - F-2 · deferred · cumulative — Backoff jitter constant duplicated in two files
      - source: cumulative review
      - note: driver accepted: cosmetic
    - F-3 · deferred · TASK-007 — 503s are not retried
      - source: https://github.com/acme/app/pull/57#discussion_r1
      - note: driver accepted for this release

pdlc inspect verify and completion read that comment back; a hand-edited one
that no longer parses is refused rather than guessed at.

The command prints JSON: `posted`, `workItem`, `itemId`, `gateState`,
`recommendation`, `head`, `findings` (the IDs this run raised), `attachments`,
plus `bouncedTo` for a bounce and `ci` when a clean run resolved the CI gate.

EXAMPLES
    pdlc post verify 142 /tmp/pdlc-verify-142.json
"""

from __future__ import annotations

import json
import sys


from pdlc.internal.workitem import (
    append_to_section,
    comments_for_issue,
    item_for_issue,
    post_blocker,
    post_comment,
    set_gate,
    task_tree,
    workflow_for_item,
)
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number
from pdlc.internal.ci_gate import resolve_ci_gate
from pdlc.internal.invalidation import bounce_stage
from pdlc.internal.pull_requests import record_open_review_comments, record_pull_requests
from pdlc.internal.vcs import has_tracked_changes, head_commit
from pdlc.internal.verification import context, reports, stack_gaps
from pdlc.domain.evidence import ReviewVerdict, compose_review
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.verification import build_report, ledger, render, render_decisions
from pdlc.internal.inputs import resolve_text, print_help, wants_help
from pdlc.domain.workflow import Event, Gate, Outcome

VERIFICATION_OUTCOMES = {
    "Approval Required": Outcome.CLEAN,
    "Changes Required": Outcome.FINDINGS,
    "Decision Required": Outcome.DECISION,
}
VERDICTS = {
    "Approval Required": ReviewVerdict.PASS,
    "Changes Required": ReviewVerdict.CHANGES_REQUIRED,
    "Decision Required": ReviewVerdict.DECISION_REQUIRED,
}


def _load(source: str) -> object:
    text = resolve_text(source, label="report")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise PdlcError(f"report is not valid JSON: {error}") from None


def post_verify(issue: str, report: str, attachment_inputs: list[dict] | None = None) -> dict:
    data = _load(report)

    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)
    # Refuse a record not at Verification / Pending|Changes Required|Stale
    # before any git or code-host work; the real outcome is checked below.
    try:
        pipeline.next_state(state, Event.VERIFIED, Outcome.FINDINGS)
    except ValueError as error:
        raise PdlcError(str(error)) from None

    if has_tracked_changes():
        raise PdlcError("tracked files differ from HEAD; verification must run against a clean checkout so HEAD is what was checked")
    tasks = task_tree(issue)
    pull_requests = record_pull_requests(issue, record=record, tasks=tasks)
    gaps = stack_gaps(pull_requests)
    if gaps:
        raise PdlcError(
            "HEAD does not include every open task PR — check out the top of the task stack, restacked: "
            + ", ".join(gaps)
        )
    open_comments = record_open_review_comments(issue, record=record, tasks=tasks)
    all_reports, _ = reports(issue, comments_for_issue(issue))
    known = ledger(all_reports)
    built = build_report(data, context(head_commit(), tasks, record.get("issueBody") or "", open_comments, known))
    recommendation = built.report.recommendation

    try:
        target = pipeline.next_state(state, Event.VERIFIED, VERIFICATION_OUTCOMES[recommendation])
        if built.bounce:
            pipeline.next_state(target, Event.BOUNCED, requested_target=built.bounce)
    except ValueError as error:
        raise PdlcError(str(error)) from None

    policy = pipeline.rework_policy
    if built.bounce and policy is None:
        raise PdlcError("this pipeline has no rework loop")
    review_body = compose_review(
        "Verification",
        VERDICTS[recommendation],
        render(built.report),
        bounce=built.bounce,
        loop=policy.name if built.bounce and policy is not None else None,
    )

    attachments = save_attachments(work_item_number(record), attachment_inputs or [])
    post_comment(issue, review_body, "REVIEW")

    append_to_section(issue, "Open Questions", [f"Deferred — {line}" for line in built.deferred])

    if built.decisions:
        post_blocker(issue, render_decisions(built.decisions), "DECISION")

    result: dict = {
        "posted": True, "workItem": int(issue), "itemId": record["id"],
        "recommendation": recommendation, "head": built.report.head,
        "findings": [entry.id for entry in built.report.findings if entry.raised],
        "attachments": attachments,
    }

    # A bounce routes a Changes Required run straight back to an upstream stage.
    # Its provenance and loop identity live in the PDLC-REVIEW comment above;
    # PDLC-INVALIDATED remains reserved for explicit driver invalidation.
    if built.bounce:
        bounced = bounce_stage(record, pipeline, target, built.bounce)
        return {**result, "gateState": bounced.gate.value, "bouncedTo": bounced.stage}

    set_gate(record["id"], target.gate.value)
    result["gateState"] = target.gate.value

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
        args, attachment_inputs = parse_attachment_arguments(raw_args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    if len(args) != 2:
        print("usage: pdlc post verify WORK_ITEM REPORT_FILE|text:JSON|-", file=sys.stderr)
        return 1

    try:
        result = post_verify(args[0], args[1], attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
