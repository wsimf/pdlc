#!/usr/bin/env python3
"""NAME
    pdlc inspect verify - read-only: verification readiness, open findings, and a pre-filled report

USAGE
    pdlc inspect verify WORK_ITEM

DESCRIPTION
    Checks whether the Work Item is ready to verify right now, then — only if
    it is — gives the verification pass everything it needs to audit without
    redoing settled work, and writes the report for this pass with every
    mechanical field already filled in.

The agent supplies judgment only where the data is genuinely ambiguous (is
this deferral durable, is this PR's disposition acceptable); every mechanical
fact is resolved here, never by the agent querying the work-item store or
`git`, or re-deriving it from the raw work item body itself.

1. Readiness: resolves the Work Item's `Status`/`Gate State`. Not
   `Status: Verification`, or a `Gate State` other than `Pending` /
   `Changes Required` / `Stale`, stops right here with why — nothing below
   is computed. The one exception is `Approval Required`: that gate means a
   clean pass is awaiting the driver, but source can move under the evidence
   afterwards, so the latest report's rows are checked for staleness first.
   Stale rows are named in the readiness verdict along with the driver-only
   command that reopens the stage, because `pdlc inspect complete` refuses the
   same record for the same reason and neither command may call it clean while
   the other calls it unproven.
2. Task completion: every delivery task's own state — mechanical facts only
   (closed, implementation recorded). An open task, a closed task with no
   implementation recorded, and any Open Questions line that mentions an open
   task are surfaced as-is with what to go confirm. Linked PRs that are not
   yet merged and green are listed too, but only as diff-base context: merge
   is a completion bar, not a verification one.
3. Open Comments: every still-unresolved review-thread comment across the
   registered PR stack, live off the code host. Each needs an action in the
   report.
4. Timeline: every PDLC evidence comment, rendered exactly as
   `pdlc inspect timeline` does by default — full bodies written to a temp
   file, a compact per-comment index inline.
5. Source: the HEAD this pass verifies. A report records that one commit, so
   HEAD must be the top of the task stack: every open task PR's head commit
   must be in it, and any that is not is named with what to check out.
6. Journeys to review: not applicable when no task is tagged `isUI`. Else,
   every `UJ-*` journey block from the parent's own `UI` section that is not
   carried forward from an earlier report, copied in full — ready to paste
   into the `user-journey-reviewer` TODO list — plus whether UX needs a fresh
   pass.
7. Findings: every finding raised by an earlier report, by `F-<n>` id, with
   its latest status. Open and decision findings are listed in full, with the
   rework-stage evidence published since the latest report; fixed and
   deferred ones compactly, so they are not raised again.
8. Report: the path of this pass's `pdlc.verify/1` report. A row is carried
   forward — result and note already filled in — when an earlier report
   settled it (confirmed, accepted, clean) and nothing it covers has changed
   since that report's HEAD: a task's claims row by the files its PRs touch,
   journeys and UX by every UI task, the cumulative review by any change.
   Changed means the file content differs between that HEAD and this one, so
   a restack alone changes nothing. Every other result is null for the pass
   to fill in; `pdlc post verify --help` documents each field.

    ## Readiness

    Ready — Gate State: Changes Required. A prior pass found something — re-verify what it flagged, plus anything the fixes touched.

    ## Task Completion

    All tasks closed with their implementation recorded.

    ## Open Comments

    PR #148:
    - @reviewer on src/cache.py:42 — this drops the lock before the write completes (https://github.com/acme/repo/pull/148#discussion_r1)

    # Timeline — 3 evidence comment(s); full bodies in /tmp/pdlc-timeline-50.md
    ...

    ## Source

    Verifying at HEAD c47d0ae13f2b… — every open task PR's head is included.

    ## Journeys to review

    Copy each of these verbatim into the TODO list; the agent cannot look them up:

    ### UJ-3: Offline retry
    - **User moment and goal:** ...

    UX: needs re-review

    ## Findings

    Open:

    - F-1 · open · TASK-007 — 503s are not retried (raised at 9f3e21c0a1b2, source: https://github.com/acme/repo/pull/148#discussion_r1)

    Published since the latest report:

    - PDLC-IMPLEMENT 2026-09-15 18:02 UTC (https://github.com/acme/repo/issues/50#issuecomment-9)

    Closed — do not raise these again:

    - F-2 · deferred — Backoff jitter constant duplicated (driver accepted: cosmetic)

    ## Report

    Filled in at /tmp/pdlc-verify-50.json — 3 row(s) carried forward, 2 to check.

or, when not ready:

    ## Readiness

    Not ready: Status is 'Testing', not Verification. That stage owns this Work Item now.

or, when a clean pass has gone stale underneath the driver:

    ## Readiness

    Not ready: verified clean, but that evidence no longer holds against current source — something has changed under these since they were verified:

    - claims TASK-007 · confirmed — RouteSyncClient retries 503 with backoff

    Do not run pdlc-complete; it blocks on this same evidence. Re-verification is a driver call: `pdlc post invalidate WORK_ITEM Verification EVIDENCE_FILE` returns the gate to Stale, after which pdlc-verify runs against the changed source.

Source reads, when HEAD misses a task:

    ## Source

    Verifying at HEAD c47d0ae13f2b… — but HEAD does not include these open task PRs; check out the top of the task stack, restacked, before auditing (pdlc post verify refuses otherwise):

    - #149 (feature/142-task-8) @ 3a1f9e2d7c4b

Open Comments reads `None.` when every review thread on the registered PR
stack is resolved. Journeys to review reads

    ## Journeys to review

    Not applicable — no UI tasks; journeys and UX are pre-filled as not applicable. Skip the `user-journey-reviewer` dispatch.

when no task is tagged `isUI`, or that every journey and UX are carried
forward when nothing needs a fresh pass. Findings reads `None.` before any
report raised one.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Callable

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import marked_comments, timeline_formatted_at
from pdlc.domain.verification import CLOSED_STATUSES, Finding, ledger
from pdlc.internal.attachments import attachments_for_item, attachments_markdown
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.pull_requests import (
    open_review_comments_section,
    record_open_review_comments,
    record_pull_requests,
)
from pdlc.internal.reporting import older_comments_notice
from pdlc.internal.scratch import scratch_path, write_scratch
from pdlc.internal.vcs import head_commit
from pdlc.internal.stack import stack_gaps
from pdlc.internal.verification import reports, reusable, skeleton, stale, ui_journeys
from pdlc.internal.workitem import (
    comments_for_issue,
    read_section,
    resolve_item,
    task_tree,
    timeline_compact,
    timeline_markdown,
    verification_evidence_comments,
    workflow_for_item,
)

NO_EVIDENCE = "No PDLC evidence comments found\n"

READY_GATES = {
    "Pending": "First verification pass.",
    "Changes Required": "A prior pass found something — re-verify what it flagged, plus anything the fixes touched.",
    "Stale": "Something upstream changed under the existing evidence — treat that evidence as unproven.",
}

TASK_MENTION = re.compile(r"TASK-\d{3}")


# Every check here is a mechanical fact off task_tree / the code host's pull
# requests — closed, hasImplementation (a pull request is attached), merged,
# checks. None of it is a judgment call; what's a judgment call is
# whether an open task's deferral is genuine, which is why that part is
# handed to the agent as candidate Open Questions lines rather than decided
# here.
def _task_completion_section(tasks: list[dict], pull_requests: list[dict], body: str) -> list[str]:
    open_tasks = [t for t in tasks if t["state"] != "CLOSED"]
    closed_without_implementation = [t for t in tasks if t["state"] == "CLOSED" and not t["hasImplementation"]]

    open_task_ids = {t["taskId"] for t in open_tasks if t.get("taskId")}
    open_questions = read_section(body, "Open Questions")
    deferral_candidates = [
        f"- {line.strip().lstrip('- ').strip()}"
        for line in open_questions.splitlines()
        if line.strip() and open_task_ids & set(TASK_MENTION.findall(line))
    ]

    # PR merge and CI state are not a Verification gate: the stack is audited
    # before it lands and a clean pass is what unblocks the merge, so requiring
    # merge here would deadlock against that. They are surfaced only as context
    # for choosing the cumulative review's diff base. Completion owns the merged-and-green bar.
    pending_prs = [
        f"- #{pr['number']} {pr['state']} checks: {pr['checks']}" + (" (draft)" if pr["isDraft"] else "")
        for pr in pull_requests
        if pr["state"] != "MERGED" or pr["checks"] not in ("SUCCESS", "NONE")
    ]
    pr_note = (
        [
            "",
            "Linked PRs not yet merged and green — expected at Verification; the stack "
            "merges after a clean pass. Use them to pick the cumulative review's diff base, not as a blocker:",
            "",
            *pending_prs,
        ]
        if pending_prs
        else []
    )

    if not (open_tasks or closed_without_implementation):
        return ["## Task Completion", "", "All tasks closed with their implementation recorded.", *pr_note]

    sections = ["## Task Completion"]
    notices = [older_comments_notice(t["number"], t.get("commentsMeta"), len(t.get("comments") or [])) for t in tasks]
    notices = [notice for notice in notices if notice]

    if open_tasks:
        sections += ["", "Open tasks — each needs a durable, on-record deferral reason, or this isn't ready:", ""]
        sections += [f"- #{t['number']} {t['title']}" for t in open_tasks]
        if deferral_candidates:
            sections += ["", "Open Questions lines mentioning one of these tasks — confirm each is a genuine, durable deferral, not just a passing note:", ""]
            sections += deferral_candidates
        else:
            sections += ["", "No Open Questions line mentions any of them."]

    if closed_without_implementation:
        sections += ["", "Closed tasks with no implementation recorded — treat as unfinished regardless of closed state:", ""]
        sections += [f"- #{t['number']} {t['title']}" for t in closed_without_implementation]

    sections += pr_note
    if notices:
        sections += ["", "> Older task comments are omitted from this view. " + "; ".join(notices) + "."]

    return sections


def _source_section(head: str, gaps: list[str]) -> list[str]:
    if not gaps:
        return ["## Source", "", f"Verifying at HEAD {head} — every open task PR's head is included."]
    return [
        "## Source",
        "",
        f"Verifying at HEAD {head} — but HEAD does not include these open task PRs; check out the top of the "
        "task stack, restacked, before auditing (pdlc post verify refuses otherwise):",
        "",
        *[f"- {gap}" for gap in gaps],
    ]


# Not a judgment call for anything it lists: a journey is listed because no
# earlier report carries it forward. What stays with the agent is only using
# this to fill the user-journey-reviewer template.
def _journeys_to_review_section(report: dict, body: str) -> list[str]:
    if report["journeys"] is None:
        return ["## Journeys to review", "", "Not applicable — no UI tasks; journeys and UX are pre-filled as not applicable. Skip the `user-journey-reviewer` dispatch."]

    journeys = ui_journeys(body)
    to_review = [row["journey"] for row in report["journeys"] if row["result"] is None]
    ux_stale = report["ux"]["result"] is None

    if not to_review and not ux_stale:
        return ["## Journeys to review", "", "Every journey and UX are carried forward — skip the `user-journey-reviewer` dispatch entirely."]

    sections = ["## Journeys to review"]
    if to_review:
        sections += ["", "Copy each of these verbatim into the TODO list; the agent cannot look them up:", ""]
        for journey_id in to_review:
            sections += [journeys[journey_id], ""]
    else:
        sections += ["", "Every journey is carried forward — omit the journey TODO bullet group; dispatch only for UX.", ""]
    sections.append("UX: " + ("needs re-review" if ux_stale else "carried forward — omit the UX TODO bullet"))
    return sections


def _finding_line(finding: Finding) -> str:
    detail = [f"raised at {finding.raised_at[:12]}"]
    if finding.source:
        detail.append(f"source: {finding.source}")
    if finding.note:
        detail.append(f"note: {finding.note}")
    return f"- {finding.id} · {finding.status} · {finding.about} — {finding.text} ({', '.join(detail)})"


# Rework-stage evidence posted after the latest verification comment: where a
# stage claims to have addressed the open findings, so the pass knows what to
# re-check. The rework stages come from the pipeline, never named here.
def _published_since(pipeline, comments: list[dict], latest: dict | None) -> list[str]:
    policy = pipeline.rework_policy
    if latest is None or policy is None:
        return []
    markers = set()
    for stage in policy.autoapprove_stages:
        try:
            markers.add(pipeline.marker_for_stage(stage))
        except ValueError:
            continue
    return [
        f"- PDLC-{comment['marker']} {timeline_formatted_at(comment['createdAt'])} ({comment.get('url', '')})"
        for comment in marked_comments(comments)
        if comment["marker"] in markers and comment["createdAt"] > latest["createdAt"]
    ]


def _findings_section(known: dict[str, Finding], published: list[str]) -> list[str]:
    if not known:
        return ["## Findings", "", "None."]
    active = [f for f in known.values() if f.status not in CLOSED_STATUSES]
    closed = [f for f in known.values() if f.status in CLOSED_STATUSES]
    sections = ["## Findings"]
    if active:
        sections += ["", "Open:", "", *[_finding_line(f) for f in active]]
        if published:
            sections += ["", "Published since the latest report:", "", *published]
    if closed:
        sections += ["", "Closed — do not raise these again:", ""]
        sections += [f"- {f.id} · {f.status} — {f.text}" + (f" ({f.note})" if f.note else "") for f in closed]
    return sections


def _report_section(issue: str, report: dict) -> list[str]:
    path = write_scratch(scratch_path(f"verify-{issue}", ".json"), json.dumps(report, indent=2) + "\n")
    rows = [*report["claims"], *(report["journeys"] or []), report["ux"], report["cumulativeReview"]]
    carried = sum(1 for row in rows if row.get("reuse", "").startswith("valid"))
    to_check = sum(1 for row in rows if row["result"] is None)
    return ["## Report", "", f"Filled in at {path} — {carried} row(s) carried forward, {to_check} to check."]


def _readiness(item: dict, stale_rows: Callable[[], list[str]]) -> tuple[bool, str]:
    """The readiness verdict, and the one sentence explaining it.

    `stale_rows` is a callable rather than a value because only the
    Approval Required branch needs it, and resolving it costs a comment read,
    a code-host file lookup per task PR, and a `git diff`.
    """
    status = item.get("Status")
    gate = item.get("Gate State")

    if status != "Verification":
        return False, f"Not ready: Status is {status!r}, not Verification. That stage owns this Work Item now."

    if gate in READY_GATES:
        return True, f"Ready — Gate State: {gate}. {READY_GATES[gate]}"

    if gate == "Approval Required":
        # The evidence that earned this gate can go stale after the fact, and
        # `pdlc inspect complete` blocks on exactly that. Checking it here too
        # is what stops the two commands answering the same question
        # differently — this one calling the record clean while completion
        # refuses it as unproven, with no command named that can break the tie.
        stale_now = stale_rows()
        if stale_now:
            return False, (
                "Not ready: verified clean, but that evidence no longer holds against "
                "current source — something has changed under these since they were verified:\n\n"
                + "\n".join(f"- {row}" for row in stale_now)
                + "\n\nDo not run pdlc-complete; it blocks on this same evidence. "
                "Re-verification is a driver call: `pdlc post invalidate WORK_ITEM "
                "Verification EVIDENCE_FILE` returns the gate to Stale, after which "
                "pdlc-verify runs against the changed source."
            )
        return False, "Not ready: already verified clean, awaiting the driver. pdlc-complete is next."

    if gate == "Decision Required":
        return False, (
            "Not ready: parked at Decision Required — a finding needs a driver call. "
            "The driver clears it via `pdlc guide decisions` "
            "(pdlc post decision), which returns it to Changes Required for a re-verify."
        )

    return False, f"Not ready: malformed Gate State {gate!r}."


# Only the Approval Required branch of `_readiness` calls this, so a record
# that is plainly not at Verification never pays for the reads or the git work.
# A latest report that does not parse (one from before pdlc.verify/1) cannot
# prove anything, so the whole of it reads as stale.
def _stale_rows(issue: str) -> list[str]:
    comments = comments_for_issue(issue)
    all_reports, latest_ok = reports(issue, comments)
    if not verification_evidence_comments(issue, comments=comments):
        return []
    if not latest_ok:
        return ["the latest verification report predates pdlc.verify/1 or no longer parses"]
    latest = all_reports[-1]
    stale_now = stale(latest, task_tree(issue))
    return [
        f"{section} {row.key} · {row.result}" + (f" — {row.note}" if row.note else "")
        for section, row in latest.rows()
        if (section, row.key) in stale_now
    ]


# The evidence timeline as `pdlc inspect timeline` renders it by default: full
# text to a temp file, a compact per-comment index inline. A long verification
# history — every review, bounce, and re-verify — then stays out of the caller's
# context while remaining one Read away.
def _timeline_block(issue: str, comments: list[dict]) -> str:
    text = timeline_markdown(issue, comments=comments)
    if text == NO_EVIDENCE:
        return text.rstrip("\n")
    path = write_scratch(scratch_path(f"timeline-{issue}"), text.rstrip("\n") + "\n")
    return timeline_compact(issue, str(path), comments=comments).rstrip("\n")


def inspect(issue: str) -> str:
    item = resolve_item(issue)
    ready, readiness_message = _readiness(item, lambda: _stale_rows(issue))
    sections = ["## Readiness", "", readiness_message, "", attachments_markdown(attachments_for_item(item))]
    if not ready:
        return "\n".join(sections) + "\n"

    pipeline, _ = workflow_for_item(item)
    tasks = task_tree(issue)
    pull_requests = record_pull_requests(issue, record=item, tasks=tasks)
    body = item.get("issueBody") or ""
    comments = comments_for_issue(issue)
    open_comments = record_open_review_comments(issue, record=item, tasks=tasks)
    head = head_commit()

    sections += ["", *_task_completion_section(tasks, pull_requests, body)]
    sections += ["", *open_review_comments_section(open_comments)]
    sections += ["", _timeline_block(issue, comments)]
    sections += ["", *_source_section(head, stack_gaps(pull_requests))]

    all_reports, _ = reports(issue, comments)
    known = ledger(all_reports)
    report = skeleton(issue, head, tasks, body, open_comments, known, reusable(all_reports, tasks))
    verification_comments = verification_evidence_comments(issue, comments=comments)
    latest = verification_comments[-1] if verification_comments else None

    sections += ["", *_journeys_to_review_section(report, body)]
    sections += ["", *_findings_section(known, _published_since(pipeline, comments, latest))]
    sections += ["", *_report_section(issue, report)]
    return "\n".join(sections) + "\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    args = command_args
    if wants_help(args):
        print_help(__doc__)
        return 0
    if len(args) != 1:
        print("usage: pdlc inspect verify WORK_ITEM", file=sys.stderr)
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
