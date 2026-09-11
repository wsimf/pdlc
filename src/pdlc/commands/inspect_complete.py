#!/usr/bin/env python3
"""NAME
    pdlc inspect complete - read-only: completion readiness check for a work item

USAGE
    pdlc inspect complete WORK_ITEM

DESCRIPTION
    Step 1 of pdlc-complete in one call. Checks whether the Work
    Item is actually ready to lock right now, then — only if it is — gives the
    mechanical facts a completion pass needs: which delivery tasks are open,
    which linked PRs aren't both merged and green, which live Open Questions the
    completion evidence must disposition, and whether the evidence in
    the latest Verification `PDLC-REVIEW` comment still holds against current source
    (the same staleness check pdlc inspect verify's reuse pass runs, applied
    here at lock time instead of audit time). The agent supplies judgment only
    where the data is genuinely ambiguous — is an open task's deferral durable,
    is unfinished work small enough to note and continue; every mechanical fact
    is resolved here, never by the agent querying the work-item store or `git` itself.

    ## Readiness

    Ready — Status: Verification, Gate State: Approval Required.

    ## Task Completion

    Open tasks — each needs a durable, on-record deferral reason, or this isn't ready:

    - #47 WORK-142-TASK-004 [CORE] Add regional cache eviction

    Linked PRs not both merged and green — confirm each is explicitly dispositioned:

    - #148 OPEN checks: PENDING

    ## Verification Evidence

    - WORK-142-TASK-007 — Confirmed: RouteShapeAnimator matches Result (Verified @ a1b2c3d)

    Stale — re-verify before completing:

    - UJ-3 — Accepted: offline retry confirmed in the running app (Verified @ a1b2c3d)

or, when not ready:

    ## Readiness

    Not ready: Status is 'Testing', not Verification. That stage owns this Work Item now.

Task Completion reads "All tasks closed; every linked PR merged with passing
checks." when there's nothing to flag. Verification Evidence reads "No
Verification review evidence found — pdlc-verify must run first." when
Verification never posted a report, or "Every verified item still holds
against current source." when nothing has gone stale since the last pass.
"""

from __future__ import annotations

import sys
from pdlc.domain.evidence import VerificationReport, parse_verification_report


from pdlc.internal.pull_requests import record_pull_requests
from pdlc.internal.attachments import attachments_for_item, attachments_markdown
from pdlc.domain.completion import completion_blockers
from pdlc.domain.completion_evidence import live_open_questions
from pdlc.internal.vcs import stale_commits
from pdlc.internal.workitem import (
    comments_for_issue,
    item_skipped_states,
    marked_comments,
    read_section,
    resolve_item,
    task_tree,
    workflow_for_item,
    verification_evidence_comments,
)
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help

def _task_completion_section(tasks: list[dict], pull_requests: list[dict]) -> list[str]:
    open_tasks = [t for t in tasks if t["state"] != "CLOSED"]
    unsettled_prs = [
        f"- #{pr['number']} {pr['state']} checks: {pr['checks']}" + (" (draft)" if pr["isDraft"] else "")
        for pr in pull_requests
        if pr["state"] != "MERGED" or pr["checks"] not in ("SUCCESS", "NONE")
    ]

    if not open_tasks and not unsettled_prs:
        return ["## Task Completion", "", "All tasks closed; every linked PR merged with passing checks."]

    sections = ["## Task Completion"]
    if open_tasks:
        sections += ["", "Open tasks — each needs a durable, on-record deferral reason, or this isn't ready:", ""]
        sections += [f"- #{t['number']} {t['title']}" for t in open_tasks]
    if unsettled_prs:
        sections += ["", "Linked PRs not both merged and green — confirm each is explicitly dispositioned:", ""]
        sections += unsettled_prs
    return sections


def _verification_evidence_section(report: VerificationReport | None, stale: list[str]) -> list[str]:
    if report is None:
        return ["## Verification Evidence", "", "No Verification review evidence found — pdlc-verify must run first."]
    still_valid = [row.text for row in report.rows if row.commit and row.text not in stale]

    sections = ["## Verification Evidence"]
    if not stale:
        sections += ["", "Every verified item still holds against current source."]
        if still_valid:
            sections += [""] + [f"- {text}" for text in still_valid]
        return sections

    sections += [""] + [f"- {text}" for text in still_valid]
    sections += ["", "Stale — re-verify before completing:", ""]
    sections += [f"- {text}" for text in stale]
    return sections


def _open_questions_section(body: str) -> list[str]:
    live = live_open_questions(read_section(body, "Open Questions"))
    if not live:
        return ["## Open Questions", "", "Nothing outstanding — the completion evidence records `- None`."]
    sections = [
        "## Open Questions",
        "",
        "Disposition every entry in the completion evidence as `<question> — Resolved: ...` or `<question> — Deferred: ...`:",
        "",
    ]
    sections += [f"- {entry}" for entry in live]
    return sections


def inspect(issue: str) -> str:
    item = resolve_item(issue)
    pipeline, _ = workflow_for_item(item)
    attachments = attachments_for_item(item)
    tasks = task_tree(issue)
    pull_requests = record_pull_requests(issue, record=item, tasks=tasks)
    body = item.get("issueBody") or ""
    comments = comments_for_issue(issue)
    verification_comments = verification_evidence_comments(issue, comments=comments)
    verification_body = verification_comments[-1]["body"] if verification_comments else None
    report = None
    stale_rows: list[str] = []
    if verification_body:
        try:
            report = parse_verification_report(verification_body)
        except PdlcError:
            pass  # completion_blockers reports malformed evidence below.
        if report is not None:
            stale = stale_commits(list(report.verified_commits))
            stale_rows = [row.text for row in report.rows if row.commit in stale]

    blockers = completion_blockers(
        pipeline=pipeline,
        status=item.get("Status", ""),
        gate=item.get("Gate State", ""),
        tasks=tasks,
        pull_requests=pull_requests,
        timeline_markers=[c["marker"] for c in marked_comments(issue, comments=comments)],
        skipped_states=item_skipped_states(item),
        verification_body=verification_body,
        stale_rows=stale_rows,
        open_questions=read_section(body, "Open Questions"),
    )

    if blockers:
        sections = ["## Readiness", "", "Not ready — resolve each of these before completing:", "", attachments_markdown(attachments), ""]
        sections += [f"- [{blocker.code}] {blocker.message}" for blocker in blockers]
        return "\n".join(sections) + "\n"

    boundary_stage, boundary_gate = pipeline.completion_boundary
    sections = ["## Readiness", "", f"Ready — Status: {boundary_stage}, Gate State: {boundary_gate.value}."]
    sections += ["", attachments_markdown(attachments)]
    sections += ["", *_task_completion_section(tasks, pull_requests)]
    sections += ["", *_verification_evidence_section(report, stale_rows)]
    sections += ["", *_open_questions_section(body)]

    return "\n".join(sections) + "\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    args = command_args
    if wants_help(args):
        print_help(__doc__)
        return 0
    if len(args) != 1:
        print("usage: pdlc inspect complete WORK_ITEM", file=sys.stderr)
        return 1
    issue = args[0]

    try:
        output = inspect(issue)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
