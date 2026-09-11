#!/usr/bin/env python3
"""Read-only: Step 1 and Step 2 of pdlc-verify in one call, and the prep
work for Step 4. Checks whether the Work Item is actually ready to audit
right now, then — only if it is — gives a resuming verification pass the
full picture it needs to avoid redoing settled work: every task and PR's
raw completion state, any still-unresolved PR review comment, the evidence
timeline, which journeys and UX still
need a fresh `user-journey-reviewer` pass and their full text ready to
copy, what still holds from the last pass, what's gone stale, what's
already fixed, and what's already deferred. The agent supplies judgment
only where the data is genuinely ambiguous (is this deferral durable, is
this PR's disposition acceptable); every mechanical fact is resolved here,
never by the agent querying the work-item store or `git`, or re-deriving it
from the raw work item body itself.

1. Readiness: resolves the Work Item's `Status`/`Gate State` and applies the
   same table pdlc-verify's Step 1 used to apply by hand. Not `Status: Verification`, or a `Gate State` other than `Pending`
   / `Changes Required` / `Stale`, stops right here with why — nothing below
   is computed, since none of it matters if this pass shouldn't be running.
   The one exception is `Approval Required`: that gate means a clean pass is
   awaiting the driver, but source can move under the evidence afterwards, so
   the reuse check in 5 runs against the last report's anchors first. Stale
   anchors are named in the readiness verdict along with the driver-only
   command that reopens the stage, because `pdlc inspect complete` refuses the
   same record for the same reason and neither command may call it clean while
   the other calls it unproven.
2. Task completion: every delivery task's own state — mechanical facts
   only (closed, implementation recorded). An open task, a closed task with
   no implementation recorded, and any Open Questions line that mentions an
   open task are surfaced as-is with what to go confirm — never silently
   passed or silently blocked. Linked PRs that are not yet merged and green
   are listed too, but only as diff-base context: merge is a completion bar,
   not a verification one, so an unmerged or CI-pending stack does not block
   this pass.
3. Open Comments: every still-unresolved review-thread comment across the
   registered PR stack, live off the code host — never inferred from PDLC's
   own evidence. Not a blocker here, the same as an unmerged PR in Task
   Completion: whether a thread is in scope, needs a fix, or can be waived is
   a judgment call left to the caller.
4. Timeline: every PDLC evidence comment, rendered exactly as
   `pdlc inspect timeline` does by default — full bodies written to a temp
   file, a compact per-comment index inline so a long history stays out of
   context.
5. Journeys to review: not applicable when no task is tagged `isUI`. Else,
   every `UJ-*` journey block from the parent's own `UI` section that is
   either new since the last verification pass or was marked stale by the
   reuse check below, copied in full — ready to paste straight into the
   `user-journey-reviewer` TODO list, since that agent cannot look a
   journey up from just its id. Plus whether UX itself needs a fresh pass.
   Empty when every journey and UX are still valid, telling the agent to
   skip the dispatch entirely rather than deciding that itself.
6. Reuse: every item in the latest Verification `PDLC-REVIEW` comment's Claims
   Audit, User Journeys, UX, and Cumulative Review sections carries a
   `(Verified @ <commit>)` marker. Since a delivery task is exactly one
   commit touching only its own files, that commit's own diff *is* the
   item's scope — no manual file list needed. For each item this runs
   `git diff-tree --no-commit-id --name-only -r <commit>` to find its
   files, then `git log <commit>..HEAD -- <files>` to see if anything's
   touched them since. The agent never runs or reads git itself.
7. Fixed: bullets listed under a `### Findings` heading in any past
   Verification `PDLC-REVIEW` comment — every one is fixed, since that section
   only ever lists fixed items.
8. Deferred: findings recorded as deferred in the parent work item body's Open
   Questions section (`"Deferred — <finding>, accepted because <reason>"`).

    pdlc inspect verify WORK_ITEM

    ## Readiness

    Ready — Gate State: Changes Required. A prior pass found something — re-verify what it flagged, plus anything the fixes touched.

    ## Task Completion

    Open tasks — each needs a durable, on-record deferral reason, or this isn't ready:

    - #47 WORK-142-TASK-004 [CORE] Add regional cache eviction

    Open Questions lines mentioning one of these tasks — confirm each is a genuine, durable deferral, not just a passing note:

    - Deferred — TASK-004 postponed to a follow-up work item, accepted because it's out of scope for this release

    Linked PRs not yet merged and green — expected at Verification; the stack
    merges after a clean pass. Use them to pick the Step 5 diff base, not as a blocker:

    - #148 OPEN checks: PENDING

    ## Open Comments

    PR #148:
    - @reviewer on src/cache.py:42 — this drops the lock before the write completes (https://github.com/acme/repo/pull/148#discussion_r1)

    # Timeline — 3 evidence comment(s); full bodies in /tmp/pdlc-timeline-50.md

    ## PRODUCT — 2026-08-01 21:14 UTC (@sudara)
       Scope: full product specification.
       Read lines 3-48 in /tmp/pdlc-timeline-50.md for the full comment.
    ...

    ## Journeys to review

    Copy each of these verbatim into the TODO list; the agent cannot look them up:

    ### UJ-3: Offline retry
    - **User moment and goal:** ...
    - **Entry points:** ...
    ...

    UX: needs re-review

    ## Still valid

    - WORK-142-TASK-007 — Confirmed: RouteShapeAnimator matches Result (Verified @ a1b2c3d)

    ## Stale — re-verify

    - UJ-3 — Accepted: offline retry confirmed in the running app (Verified @ a1b2c3d)

    ## Fixed by previous runs

    - Route line snapped to wrong profile on regen (Verified @ b2c3d4e)

    ## Deferred

    - Elevation gain rounding drifts by 2m, accepted because it's within tolerance

    Important: do not report these deferred items again — they are already
    known and were decided to be skipped.

or, when not ready:

    ## Readiness

    Not ready: Status is 'Testing', not Verification. That stage owns this Work Item now.

or, when a clean pass has gone stale underneath the driver:

    ## Readiness

    Not ready: verified clean, but that evidence no longer holds against current source — something has touched these since they were verified:

    - FR-1 holds (Verified @ 0a1a3cb)

    Do not run pdlc-complete; it blocks on this same evidence. Re-verification is a driver call: `pdlc post invalidate WORK_ITEM Verification EVIDENCE_FILE` returns the gate to Stale, after which pdlc-verify runs against the changed source.

Task Completion reads

    ## Task Completion

    All tasks closed with their implementation recorded.

when there's no task to flag (an unmerged-PR list may still follow as diff-base
context). Open Comments reads

    ## Open Comments

    None.

when every review thread on the registered PR stack is resolved (or none is
registered — nothing distinguishes the two, since neither is a finding).
Journeys to review reads

    ## Journeys to review

    Not applicable — no UI tasks; record journeys and UX as not applicable and skip Step 4.

when no task is tagged `isUI`, or

    ## Journeys to review

    Every journey and UX are still valid — skip the `user-journey-reviewer` dispatch entirely.

when nothing needs a fresh pass. Still valid / Stale are omitted when the
latest verification comment has no `(Verified @ ...)` items to check.
Fixed by previous runs and Deferred read `None` when there's nothing for
them, or with no verification run yet at all, everything after Readiness,
Task Completion, Open Comments, Timeline, and Journeys to review is just:

    No verification step found
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Callable
from pdlc.domain.evidence import parse_verification_report
from pdlc.internal.reporting import older_comments_notice


from pdlc.internal.pull_requests import record_open_review_comments, record_pull_requests
from pdlc.internal.attachments import attachments_for_item, attachments_markdown
from pdlc.internal.vcs import stale_commits
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.workitem import (
    comments_for_issue,
    read_section,
    ref_label,
    resolve_item,
    task_tree,
    timeline_compact,
    timeline_markdown,
    verification_evidence_comments,
)

NO_EVIDENCE = "No PDLC evidence comments found\n"

READY_GATES = {
    "Pending": "First verification pass.",
    "Changes Required": "A prior pass found something — re-verify what it flagged, plus anything the fixes touched.",
    "Stale": "Something upstream changed under the existing evidence — treat that evidence as unproven.",
}


VERIFIED_AT = re.compile(r"\(Verified @ ([^)]+)\)\s*$")
DEFERRED_PATTERN = re.compile(r"^-?\s*Deferred\s*[—-]\s*(.+?)\s*$")
TASK_MENTION = re.compile(r"TASK-\d{3}")
JOURNEY_HEADING = re.compile(r"^#{1,6}\s*(UJ-\d+)\b")
JOURNEY_ID_IN_BULLET = re.compile(r"^(UJ-\d+)\b")


# Every bullet here is fixed by construction, since Findings only ever
# lists what a pass fixed and re-verified. The `(Verified @ ...)` marker on
# each line is pdlc post verify's, not the agent's — strip it here
# rather than exposing it as something the caller must parse itself.
def _fixed_findings_in(body: str) -> list[str]:
    return list(parse_verification_report(body).findings)


def _deferred_findings_in(body: str) -> list[str]:
    open_questions = read_section(body, "Open Questions")
    deferred = []
    for line in open_questions.splitlines():
        match = DEFERRED_PATTERN.match(line.strip())
        if match:
            deferred.append(match.group(1))
    return deferred


# Every item in the latest verification comment's Claims Audit / User
# Journeys / UX / Cumulative Review sections, judged valid or stale from its own
# `(Verified @ <commit>)` commit's diff against HEAD. Section names are kept
# per item so callers can filter by kind (e.g. journeys-to-review needs just
# User Journeys and UX) without re-parsing.
def _reuse_items(latest_verification_body: str) -> list[dict]:
    report = parse_verification_report(latest_verification_body)
    stale = stale_commits(list(report.verified_commits))
    return [
        {"section": row.section, "text": row.text, "stale": row.commit in stale}
        for row in report.rows
        if row.commit
    ]


def _reuse_sections(items: list[dict]) -> list[str]:
    valid = [item["text"] for item in items if not item["stale"]]
    stale = [item["text"] for item in items if item["stale"]]

    if not valid and not stale:
        return []

    sections = ["## Still valid", ""]
    sections.append("\n".join(f"- {item}" for item in valid) if valid else "None")
    sections += ["", "## Stale — re-verify", ""]
    sections.append("\n".join(f"- {item}" for item in stale) if stale else "None")
    return sections


# Every `### UJ-N: ...` journey block in the parent's own UI section, keyed
# by id, full text included — pdlc-ui-planner's own fragment format. This is
# what lets journeys-to-review hand the agent a journey ready to paste into
# the user-journey-reviewer TODO list instead of a bare id it can't look up.
def _ui_journeys(body: str) -> dict[str, str]:
    ui_section = read_section(body, "UI")
    journeys: dict[str, list[str]] = {}
    journey_id: str | None = None
    for raw_line in ui_section.splitlines():
        match = JOURNEY_HEADING.match(raw_line.strip())
        if match:
            journey_id = match.group(1)
            journeys[journey_id] = [raw_line.rstrip()]
            continue
        if journey_id:
            journeys[journey_id].append(raw_line.rstrip())
    return {jid: "\n".join(lines).strip() for jid, lines in journeys.items()}


# Not a judgment call for anything it lists: a journey is either new since
# the last pass (absent from every previous report) or the reuse check
# above marked it stale — either way it needs a fresh look. What stays with
# the agent is only using this to fill the user-journey-reviewer template.
def _journeys_to_review_section(tasks: list[dict], body: str, reuse_items: list[dict]) -> list[str]:
    if not any(task["isUI"] for task in tasks):
        return ["## Journeys to review", "", "Not applicable — no UI tasks; record journeys and UX as not applicable and skip Step 4."]

    ui_journeys = _ui_journeys(body)
    journey_items = [item for item in reuse_items if item["section"] == "User Journeys"]

    seen_ids: set[str] = set()
    stale_ids: list[str] = []
    for item in journey_items:
        match = JOURNEY_ID_IN_BULLET.match(item["text"])
        if not match:
            continue
        journey_id = match.group(1)
        seen_ids.add(journey_id)
        if item["stale"]:
            stale_ids.append(journey_id)

    to_review = [jid for jid in ui_journeys if jid in stale_ids or jid not in seen_ids]

    ux_items = [item for item in reuse_items if item["section"] == "UX"]
    ux_stale = not ux_items or any(item["stale"] for item in ux_items)

    if not to_review and not ux_stale:
        return ["## Journeys to review", "", "Every journey and UX are still valid — skip the `user-journey-reviewer` dispatch entirely."]

    sections = ["## Journeys to review"]

    if to_review:
        sections += ["", "Copy each of these verbatim into the TODO list; the agent cannot look them up:", ""]
        for journey_id in to_review:
            text = ui_journeys.get(journey_id)
            if text:
                sections += [text, ""]
            else:
                sections += [f"{journey_id} — referenced by a previous report but not found in the current UI section; confirm the mapping manually.", ""]
    else:
        sections += ["", "Every journey is still valid — omit the journey TODO bullet group; dispatch only for UX.", ""]

    sections.append("UX: " + ("needs re-review" if ux_stale else "still valid — omit the UX TODO bullet"))
    return sections


# Every check here is a mechanical fact off task_tree / the code host's pull
# requests — closed, hasImplementation (implementation recorded for the task), merged,
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
    # for choosing the Step 5 diff base. Completion owns the merged-and-green bar.
    pending_prs = [
        f"- #{pr['number']} {pr['state']} checks: {pr['checks']}" + (" (draft)" if pr["isDraft"] else "")
        for pr in pull_requests
        if pr["state"] != "MERGED" or pr["checks"] not in ("SUCCESS", "NONE")
    ]
    pr_note = (
        [
            "",
            "Linked PRs not yet merged and green — expected at Verification; the stack "
            "merges after a clean pass. Use them to pick the Step 5 diff base, not as a blocker:",
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


# Live review-thread state off the registered PR stack, not evidence PDLC
# itself recorded — this is the same "not a blocker, context to judge" shape
# as the pending-PR note in Task Completion. Nothing here resolves a thread
# or decides it's in scope; that judgment stays with the caller.
def _open_comments_section(open_comments: list[dict]) -> list[str]:
    if not open_comments:
        return ["## Open Comments", "", "None."]

    sections = ["## Open Comments", ""]
    by_pr: dict[int, list[dict]] = {}
    for comment in open_comments:
        by_pr.setdefault(comment["pr"], []).append(comment)

    for number in sorted(by_pr):
        sections.append(f"PR #{number}:")
        for comment in by_pr[number]:
            where = f" on {comment['path']}:{comment['line']}" if comment.get("path") else ""
            sections.append(f"- @{comment['author']}{where} — {comment['body']} ({comment['url']})")
        sections.append("")
    return sections[:-1] if sections[-1] == "" else sections


def _readiness(item: dict, stale_anchors: Callable[[], list[str]]) -> tuple[bool, str]:
    """The readiness verdict, and the one sentence explaining it.

    `stale_anchors` is a callable rather than a value because only the
    Approval Required branch needs it, and resolving it costs a comment read
    plus one `git` pair per verified commit.
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
        stale = stale_anchors()
        if stale:
            return False, (
                "Not ready: verified clean, but that evidence no longer holds against "
                "current source — something has touched these since they were verified:\n\n"
                + "\n".join(f"- {row}" for row in stale)
                + "\n\nDo not run pdlc-complete; it blocks on this same evidence. "
                "Re-verification is a driver call: `pdlc post invalidate WORK_ITEM "
                "Verification EVIDENCE_FILE` returns the gate to Stale, after which "
                "pdlc-verify runs against the changed source."
            )
        return False, "Not ready: already verified clean, awaiting the driver. pdlc-complete is next."

    if gate == "Decision Required":
        return False, (
            "Not ready: parked at Decision Required — a finding needs a driver call. "
            "The driver clears it via references/decision-resolver-workflow.md "
            "(pdlc post decision), which returns it to Changes Required for a re-verify."
        )

    return False, f"Not ready: malformed Gate State {gate!r}."


# Only the Approval Required branch of `_readiness` calls this, so a record
# that is plainly not at Verification never pays for the comment read or the
# git work.
def _stale_anchors(issue: str) -> list[str]:
    comments = verification_evidence_comments(issue)
    if not comments:
        return []
    return [item["text"] for item in _reuse_items(comments[-1]["body"]) if item["stale"]]


# The evidence timeline as `pdlc inspect timeline` renders it by default: full
# text to a temp file, a compact per-comment index inline. A long verification
# history — every review, bounce, and re-verify — then stays out of the caller's
# context while remaining one Read away.
def _timeline_block(issue: str, comments: list[dict]) -> str:
    text = timeline_markdown(issue, comments=comments)
    if text == NO_EVIDENCE:
        return text.rstrip("\n")
    path = Path(tempfile.gettempdir()) / f"{ref_label()}-timeline-{issue}.md"
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    return timeline_compact(issue, str(path), comments=comments).rstrip("\n")


def inspect(issue: str) -> str:
    item = resolve_item(issue)
    ready, readiness_message = _readiness(item, lambda: _stale_anchors(issue))
    sections = ["## Readiness", "", readiness_message, "", attachments_markdown(attachments_for_item(item))]
    if not ready:
        return "\n".join(sections) + "\n"

    tasks = task_tree(issue)
    pull_requests = record_pull_requests(issue, record=item, tasks=tasks)
    body = item.get("issueBody") or ""
    comments = comments_for_issue(issue)

    sections += ["", *_task_completion_section(tasks, pull_requests, body)]
    sections += ["", *_open_comments_section(record_open_review_comments(issue, record=item, tasks=tasks))]
    sections += ["", _timeline_block(issue, comments)]

    verification_comments = verification_evidence_comments(issue, comments=comments)
    reuse_items = _reuse_items(verification_comments[-1]["body"]) if verification_comments else []

    sections += ["", *_journeys_to_review_section(tasks, body, reuse_items)]

    if not verification_comments:
        sections += ["", "No verification step found"]
        return "\n".join(sections) + "\n"

    fixed: dict[str, str] = {}
    for comment in verification_comments:
        for text in _fixed_findings_in(comment["body"]):
            fixed[VERIFIED_AT.sub("", text).strip()] = text

    deferred = _deferred_findings_in(body)

    reuse = _reuse_sections(reuse_items)
    if reuse:
        sections += ["", *reuse]

    sections += ["", "## Fixed by previous runs", ""]
    sections.append("\n".join(f"- {text}" for text in fixed.values()) if fixed else "None")
    sections += ["", "## Deferred", ""]
    sections.append("\n".join(f"- {text}" for text in deferred) if deferred else "None")

    if deferred:
        sections += ["", "Important: do not report these deferred items again — they are already known and were decided to be skipped."]

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
