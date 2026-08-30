#!/usr/bin/env python3
"""Read-only: Step 1 of pdlc-complete in one call. Checks whether the Work
Item is actually ready to lock right now, then — only if it is — gives the
mechanical facts a completion pass needs: which delivery tasks are open,
which linked PRs aren't both merged and green, which live Open Questions the
completion evidence must disposition, and whether the evidence in
the latest `PDLC-VERIFICATION` comment still holds against current source
(the same staleness check pdlc-inspect-verify.py's reuse pass runs, applied
here at lock time instead of audit time). The agent supplies judgment only
where the data is genuinely ambiguous — is an open task's deferral durable,
is unfinished work small enough to note and continue; every mechanical fact
is resolved here, never by the agent querying the work-item store or `git` itself.

    pdlc-inspect-complete.py WORK_ITEM

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

    - UJ-3 — Accepted: offline retry confirmed on simulator (Verified @ a1b2c3d)

or, when not ready:

    ## Readiness

    Not ready: Status is 'Testing', not Verification. That stage owns this Work Item now.

Task Completion reads "All tasks closed; every linked PR merged with passing
checks." when there's nothing to flag. Verification Evidence reads "No
PDLC-VERIFICATION comment found — pdlc-verify must run first." when
Verification never posted a report, or "Every verified item still holds
against current source." when nothing has gone stale since the last pass.
"""

from __future__ import annotations

import sys
from pathlib import Path


from pdlc.hosts.code_host import get_code_host  # type: ignore
from pdlc.internal.attachments import attachments_for_item, attachments_markdown  # type: ignore
from pdlc.domain.completion import completion_blockers  # type: ignore
from pdlc.domain.completion_evidence import live_open_questions  # type: ignore
from pdlc.internal.vcs import files_touched_by as _files_touched_by, is_stale as _is_stale  # type: ignore
from pdlc.internal.workitem import (  # type: ignore
    comments_for_issue,
    find_marked_comments,
    item_skipped_states,
    marked_comments,
    read_section,
    resolve_item,
    task_tree,
)
from pdlc.domain.lifecycle import PdlcError, print_help, wants_help  # type: ignore

import re

REPORT_HEADING = re.compile(r"^#{1,6}\s*(Claims Audit|User Journeys|UX|Ultra Review)\s*$", re.IGNORECASE)
HEADING_PATTERN = re.compile(r"^#{1,6}\s")
BULLET_PATTERN = re.compile(r"^-\s+(.+?)\s*$")
VERIFIED_AT = re.compile(r"\(Verified @ ([^)]+)\)\s*$")


def _bullets_by_section(body: str) -> list[str]:
    items = []
    section = None
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if REPORT_HEADING.match(line):
            section = True
            continue
        if section and HEADING_PATTERN.match(line):
            section = None
            continue
        if not section:
            continue
        match = BULLET_PATTERN.match(line)
        if match:
            items.append(match.group(1))
    return items


def _task_completion_section(tasks: list[dict], pull_requests: list[dict]) -> list[str]:
    open_tasks = [t for t in tasks if t["state"] != "CLOSED"]
    unsettled_prs = [
        f"- #{pr['number']} {pr['state']} checks: {pr['checks']}" + (" (draft)" if pr["isDraft"] else "")
        for pr in pull_requests
        if pr["relation"] == "closes" and (pr["state"] != "MERGED" or pr["checks"] not in ("SUCCESS", "NONE"))
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


def _verification_evidence_section(issue: str) -> list[str]:
    verification_comments = find_marked_comments(issue, "VERIFICATION")
    if not verification_comments:
        return ["## Verification Evidence", "", "No PDLC-VERIFICATION comment found — pdlc-verify must run first."]

    items = _bullets_by_section(verification_comments[-1]["body"])
    still_valid = []
    stale = []
    for text in items:
        match = VERIFIED_AT.search(text)
        if not match:
            continue
        commit = match.group(1)
        (stale if _is_stale(commit, _files_touched_by(commit)) else still_valid).append(text)

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


def _stale_rows(issue: str) -> list[str]:
    verification_comments = find_marked_comments(issue, "VERIFICATION")
    if not verification_comments:
        return []
    rows = []
    for text in _bullets_by_section(verification_comments[-1]["body"]):
        match = VERIFIED_AT.search(text)
        if match and _is_stale(match.group(1), _files_touched_by(match.group(1))):
            rows.append(text)
    return rows


def inspect(issue: str) -> str:
    item = resolve_item(issue)
    attachments = attachments_for_item(item)
    tasks = task_tree(issue)
    pull_requests = get_code_host().pull_requests(issue)
    body = item.get("issueBody") or ""
    comments = comments_for_issue(issue)
    verification_comments = find_marked_comments(issue, "VERIFICATION", comments=comments)
    verification_body = verification_comments[-1]["body"] if verification_comments else None

    blockers = completion_blockers(
        status=item.get("Status", ""),
        gate=item.get("Gate State", ""),
        tasks=tasks,
        pull_requests=pull_requests,
        timeline_markers=[c["marker"] for c in marked_comments(issue, comments=comments)],
        skipped_states=item_skipped_states(item),
        verification_body=verification_body,
        stale_rows=_stale_rows(issue) if verification_body else None,
        open_questions=read_section(body, "Open Questions"),
    )

    if blockers:
        sections = ["## Readiness", "", "Not ready — resolve each of these before completing:", "", attachments_markdown(attachments), ""]
        sections += [f"- [{blocker.code}] {blocker.message}" for blocker in blockers]
        return "\n".join(sections) + "\n"

    sections = ["## Readiness", "", "Ready — Status: Verification, Gate State: Approval Required."]
    sections += ["", attachments_markdown(attachments)]
    sections += ["", *_task_completion_section(tasks, pull_requests)]
    sections += ["", *_verification_evidence_section(issue)]
    sections += ["", *_open_questions_section(body)]

    return "\n".join(sections) + "\n"


def main() -> int:
    args = sys.argv[1:]
    if wants_help(args):
        print_help(__doc__)
        return 0
    if len(args) != 1:
        print("usage: pdlc-inspect-complete.py WORK_ITEM", file=sys.stderr)
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
