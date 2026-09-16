"""Record-side facts a verification report is checked against, shared by
`pdlc inspect verify`, `pdlc post verify`, and completion so they resolve the
same tasks, journeys, findings, and staleness from the same reads."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.verification import (
    CLOSED_STATUSES,
    CUMULATIVE_KEY,
    SCHEMA,
    SETTLED_RESULTS,
    UX_KEY,
    Finding,
    Report,
    Row,
    VerifyContext,
    ledger,
    parse,
    stale_rows,
)
from pdlc.hosts.code_host import get_code_host
from pdlc.internal.vcs import changed_files, contains_commit
from pdlc.internal.workitem import read_section, verification_evidence_comments

_JOURNEY_HEADING = re.compile(r"^#{1,6}\s*(UJ-\d+)\b")


def task_key(task: dict) -> str:
    """The id a claims row names a delivery task by."""
    return task.get("taskId") or f"#{task['number']}"


def claim_tasks(tasks: list[dict]) -> list[dict]:
    """Delivery tasks whose claims a report must audit: every closed task."""
    return [task for task in tasks if task["state"] == "CLOSED"]


def ui_journeys(body: str) -> dict[str, str]:
    """Every `### UJ-N: ...` block in the parent's UI section, full text, by id."""
    journeys: dict[str, list[str]] = {}
    journey_id: str | None = None
    for raw_line in read_section(body, "UI").splitlines():
        match = _JOURNEY_HEADING.match(raw_line.strip())
        if match:
            journey_id = match.group(1)
            journeys[journey_id] = [raw_line.rstrip()]
            continue
        if journey_id:
            journeys[journey_id].append(raw_line.rstrip())
    return {jid: "\n".join(lines).strip() for jid, lines in journeys.items()}


def reports(issue: str, comments: list[dict]) -> tuple[list[Report], bool]:
    """Every verification report that parses, oldest first, and whether the
    latest verification comment was one of them. Reports from before
    `pdlc.verify/1` and hand-broken ones are skipped."""
    parsed: list[Report] = []
    latest_ok = False
    for comment in verification_evidence_comments(issue, comments=comments):
        try:
            parsed.append(parse(comment["body"]))
            latest_ok = True
        except PdlcError:
            latest_ok = False
    return parsed, latest_ok


def context(
    head: str, tasks: list[dict], body: str, open_comments: list[dict], known: dict[str, Finding],
) -> VerifyContext:
    has_ui = any(task.get("isUI") for task in tasks)
    return VerifyContext(
        head=head,
        run_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        tasks=tuple(task_key(task) for task in claim_tasks(tasks)),
        journeys=tuple(ui_journeys(body)) if has_ui else None,
        open_comments=tuple(comment["url"] for comment in open_comments if comment.get("url")),
        findings=known,
    )


def stack_gaps(pull_requests: list[dict]) -> list[str]:
    """Open task PRs whose head commit HEAD does not include — a lower branch
    checked out, or a fix not yet restacked. Merged PRs are skipped: a squash
    merge rewrites their commits, so their code arrives through the base."""
    return [
        f"#{pr['number']} ({pr.get('branch') or 'unknown branch'}) @ {pr['headSha'][:12]}"
        for pr in pull_requests
        if pr.get("state") == "OPEN" and pr.get("headSha") and not contains_commit(pr["headSha"])
    ]


def task_files(tasks: list[dict]) -> dict[str, set[str] | None]:
    """Every closed task's PR files off the code host; None when a task has no
    registered PR, so its evidence is never treated as still holding."""
    host = get_code_host()
    cache: dict[int, list[str]] = {}
    files: dict[str, set[str] | None] = {}
    for task in claim_tasks(tasks):
        numbers = task.get("prs") or []
        if not numbers:
            files[task_key(task)] = None
            continue
        found: set[str] = set()
        for number in numbers:
            if number not in cache:
                cache[number] = host.pull_request_files(number)
            found.update(cache[number])
        files[task_key(task)] = found
    return files


def stale(report: Report, tasks: list[dict]) -> set[tuple[str, str]]:
    """Rows of `report` that no longer hold against HEAD."""
    ui_tasks = {task_key(task) for task in claim_tasks(tasks) if task.get("isUI")}
    return stale_rows(report, changed_files(report.head), task_files(tasks), ui_tasks)


def reusable(all_reports: list[Report], tasks: list[dict]) -> dict[tuple[str, str], tuple[Row, str]]:
    """Rows a new pass may carry forward, each with the HEAD it was checked at.

    Per row, the newest report that settled it (confirmed, accepted, clean)
    wins while nothing it covers changed since that report's HEAD. A newer
    `not_run` row looks further back; a newer failed row, or a settled one gone
    stale, ends the search — its evidence no longer holds.
    """
    ui_tasks = {task_key(task) for task in claim_tasks(tasks) if task.get("isUI")}
    files = task_files(tasks) if all_reports else {}
    stale_at: dict[str, set[tuple[str, str]]] = {}
    found: dict[tuple[str, str], tuple[Row, str]] = {}
    closed: set[tuple[str, str]] = set()
    for report in reversed(all_reports):
        if report.head not in stale_at:
            stale_at[report.head] = stale_rows(report, changed_files(report.head), files, ui_tasks)
        for section, row in report.rows():
            key = (section, row.key)
            # not_applicable is recomputed from the tasks on every pass.
            if key in found or key in closed or row.result in ("not_run", "not_applicable"):
                continue
            if row.result in SETTLED_RESULTS and key not in stale_at[report.head]:
                found[key] = (row, report.head)
            else:
                closed.add(key)
    return found


def skeleton(
    issue: str,
    head: str,
    tasks: list[dict],
    body: str,
    open_comments: list[dict],
    known: dict[str, Finding],
    reuse: dict[tuple[str, str], tuple[Row, str]],
) -> dict[str, Any]:
    """The `pdlc.verify/1` report for this pass with every mechanical field
    filled in: carried-forward rows keep their result and note, everything
    else the verifier must check is null."""

    def row(section: str, key: str, id_field: str, **extra: Any) -> dict[str, Any]:
        carried = reuse.get((section, key))
        entry: dict[str, Any] = {id_field: key, **extra} if id_field else dict(extra)
        if carried:
            entry.update(reuse=f"valid — checked at {carried[1][:12]}", result=carried[0].result, note=carried[0].note)
        else:
            entry.update(reuse="check", result=None, note="")
        return entry

    has_ui = any(task.get("isUI") for task in tasks)
    ux = row("ux", UX_KEY, "") if has_ui else {"result": "not_applicable", "note": ""}
    cumulative = row("cumulative", CUMULATIVE_KEY, "")
    cumulative.setdefault("scope", "")
    return {
        "schema": SCHEMA,
        "workItem": int(issue) if str(issue).isdigit() else issue,
        "head": head,
        "claims": [row("claims", task_key(task), "task", title=task.get("title", "")) for task in claim_tasks(tasks)],
        "journeys": [row("journeys", jid, "journey") for jid in ui_journeys(body)] if has_ui else None,
        "ux": ux,
        "cumulativeReview": cumulative,
        "openComments": [
            {"url": c["url"], "author": c.get("author", ""), "excerpt": " ".join(str(c.get("body", "")).split())[:200],
             "action": None, "note": ""}
            for c in open_comments if c.get("url")
        ],
        "findings": [
            {"id": f.id, "about": f.about, "text": f.text,
             "status": None if f.status == "decision" else f.status, "note": ""}
            for f in known.values() if f.status not in CLOSED_STATUSES
        ],
        "newFindings": [],
        "bounce": None,
    }


def verification_state(issue: str, comments: list[dict], tasks: list[dict]) -> tuple[str | None, Report | None, list[str], list[str]]:
    """The latest verification body, its parsed report (None when it does not
    parse — completion_blockers reports that), its stale rows, and every
    finding still open or awaiting a decision. Shared by pdlc inspect complete and pdlc post complete."""
    verification_comments = verification_evidence_comments(issue, comments=comments)
    if not verification_comments:
        return None, None, [], []
    body = verification_comments[-1]["body"]
    all_reports, latest_ok = reports(issue, comments)
    if not latest_ok:
        return body, None, [], []
    report = all_reports[-1]
    stale_now = stale(report, tasks)
    stale_rows = [
        f"{section} {row.key} · {row.result}" for section, row in report.rows() if (section, row.key) in stale_now
    ]
    open_findings = [
        f"{finding.id} · {finding.status} — {finding.text}"
        for finding in ledger(all_reports).values() if finding.status not in CLOSED_STATUSES
    ]
    return body, report, stale_rows, open_findings
