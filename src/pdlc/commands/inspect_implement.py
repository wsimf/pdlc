#!/usr/bin/env python3
"""NAME
    pdlc inspect implement - read-only: whether Implementation is due, its mode, and the one unit to work next

USAGE
    pdlc inspect implement WORK_ITEM

DESCRIPTION
    Resolves whether Implementation is due for a record and, if so, which mode
    it is in and the single unit of work to do next: one task to implement, one
    task to fix, the change requests to triage, or nothing but the publish.

Every call prints exactly one unit. Do that unit, land it with the command
under `## Publish`, and run this again for the next one; the loop ends when
`mode: none` names the stage publish, or says what it is waiting on.

`## Readiness` reports whether the stage is due (Status Implementation, gate
Pending / Changes Required / Stale, not skipped). A task that is OPEN but
already carries a live `## Implementation` is an inconsistency this command
will not route around: readiness names it and the output stops there.

`## Mode` is decided from record and live host state, first match wins:

- `implement`: the gate is Pending or Stale and a delivery task is eligible —
  OPEN, technically planned, and not yet implemented (or its implementation
  invalidated). The unit is the first such task in CORE-before-UI then
  task-number order.
- `rework`: an implemented task's pull request has an unresolved review thread
  or a red check. The unit is the lowest such task in the stack. Under Pending
  and Stale this is consulted only once no task is eligible, so new tasks come
  first; under Changes Required there are none, so fixes come first.
- `triage`: no task needs a fix, but a review's Changes Required, a
  Verification bounce, or a decision resolution is open against the stage.
  The unit is every such request in full; the caller splits them into findings
  and fixes each on its owning task. They stay open until the stage publishes.
- `none`: nothing eligible, nothing to fix, nothing to triage. `## Checks`
  reads every registered pull request's checks and `## Next Task` directs the
  caller to continue the workflow through the stage publish. With unplanned
  tasks left, the record is waiting on planning instead.

A pull request whose checks are pending or running is never a unit and never
holds the loop: the next unit or stage publish proceeds while it runs. Review
threads and check state are live host state, read fresh each call, not evidence
PDLC recorded; nothing here resolves a thread or judges a request.

`## Attachments` lists the record's attachments. The unit section (`## Next Task`, `## Next Fix`, or `## Open
Requests`) ends with a `Next:` sentence naming the one read-only hop before
doing the work; `## Publish` is always last and holds the one mutating command
that lands the unit or the stage.

`## Next Fix` names the implemented task, its pull request, and the live
threads and red checks on it. When the driver has answered a decision since
the stage last published, the resolution is printed under `#### Decisions` so a
thread that was escalated is settled per the answer on this pass instead of
escalated again.

`## Next Task` names the task with its `branch:`; `pdlc checkout` puts the
working tree on it, so no stack setup is printed here. A `blocked:` line
replaces the handoff when the worktree stacks after another work item that has
no implemented task pull request yet. A Stale task also carries a
`reconcile:` line and its `#### Invalidation` comment in full.

Not ready, or nothing to do, is reported plainly rather than raised.

    ## Readiness

    Ready — Gate State: Changes Required.

    ## Mode

    mode: rework

    ## Attachments

    None

    ## Next Fix

    ### WORK-142-TASK-002 [CORE] Chart data loader
    number: 49
    taskId: TASK-002
    pr: 151
    branch: pdlc/record-142/task-002
    state: CLOSED

    This task is already implemented and its current changes are published in
    PR #151. Run `pdlc checkout 49` to put the working tree on that PR's
    branch; every fix below lands as a new commit on top of it, after the
    implementer has investigated the current implementation.

    #### Unresolved threads (1)
    - @reviewer on src/chart.py:42 — this drops the retry (https://.../#discussion_r1)

    Next: Run `pdlc inspect task 49` for the implementer sub-agent under
    `## Agent`, then dispatch that sub-agent to fix every thread and failing
    check above on the checked-out branch.

    ## Publish

    After every thread and failing check above is fixed and the files are
    committed, run `pdlc post implement-task 49 SUMMARY` to re-land the fix on
    the task's PR; the task stays closed.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from pdlc.domain.changes import SOURCE_LABELS, ChangeRequest, open_change_requests
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import MARKER_PREFIX, evidence_comment_text, item_gate, timeline_formatted_at
from pdlc.internal.attachments import attachments_for_item, attachments_markdown
from pdlc.internal.ci_gate import check_state
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.pull_requests import record_open_review_comments, record_pull_requests
from pdlc.internal.stack import after_predecessor, task_branch_name
from pdlc.internal.workitem import due_next, item_branch_slug, pipeline_for_item, record_snapshot
from pdlc.internal.failure import report_failure

# The change-request sources whose text is the whole record's, not one task's:
# they cannot be attributed to a pull request, so they form the triage unit.
_TRIAGE_SOURCES = ("review", "bounce", "resolution")

@dataclass(frozen=True)
class _Fix:
    """One implemented task with something live to fix on its pull request(s)."""

    task: dict
    pr: int
    threads: list[dict]
    red: list[dict]


def _readiness(item: dict, delivery: list[dict]) -> tuple[bool, str]:
    status = item.get("Status")
    gate = item_gate(item)
    if status != "Implementation":
        return False, f"Not ready: Status is {status!r}, not Implementation. That stage owns this Work Item now."
    due = due_next(item)
    if due["action"] != "pdlc-implement":
        return False, f"Not ready: Gate State is {gate!r}. {due['reason'].capitalize()}."
    for task in sorted(delivery, key=lambda t: t["number"]):
        if task["state"] == "OPEN" and task["hasImplementation"] and not task["implementationInvalidated"]:
            return False, (
                f"Not ready: {task['title']} (number {task['number']}) has an implementation recorded but is "
                f"still open. Close it with `pdlc post implement-task {task['number']} SUMMARY` or reopen its "
                "implementation with `pdlc post invalidate`."
            )
    return True, f"Ready — Gate State: {gate}."


def _eligible(task: dict) -> bool:
    return (
        task["state"] == "OPEN"
        and task["hasPlan"]
        and (not task["hasImplementation"] or task["implementationInvalidated"])
    )


def _stack_order(task: dict) -> tuple[bool, int]:
    # Tasks are implemented, and so stacked, CORE before UI then by number.
    return (task["isUI"], task["number"])


def _latest_invalidation(task: dict, comments: list[dict]) -> dict | None:
    """The task's own PDLC-INVALIDATED comment, or the record's, newest first."""
    for pool in (task.get("commentObjects") or [], comments):
        marked = [
            comment for comment in pool
            if (match := MARKER_PREFIX.match(comment.get("body") or "")) and match.group(1) == "INVALIDATED"
        ]
        if marked:
            return max(marked, key=lambda comment: comment.get("createdAt") or "")
    return None


def _fixes(delivery: list[dict], pull_requests: list[dict], threads: list[dict]) -> list[_Fix]:
    """Every implemented task with an unresolved thread or a red check on one of
    its pull requests, lowest in the stack first. A registered PR no task owns
    (the record-level top PR) is charged to the top task."""
    implemented = sorted((t for t in delivery if t.get("prs")), key=_stack_order)
    if not implemented:
        return []
    owner: dict[int, dict] = {}
    for task in implemented:
        for number in task["prs"]:
            owner.setdefault(number, task)
    top = implemented[-1]

    threads_by_task: dict[int, list[dict]] = {}
    for thread in threads:
        task = owner.get(thread["pr"], top)
        threads_by_task.setdefault(task["number"], []).append(thread)
    red_by_task: dict[int, list[dict]] = {}
    for pr in pull_requests:
        if check_state(pr.get("checks")) == "red":
            task = owner.get(pr["number"], top)
            red_by_task.setdefault(task["number"], []).append(pr)

    fixes = []
    for task in implemented:
        task_threads = threads_by_task.get(task["number"], [])
        task_red = red_by_task.get(task["number"], [])
        if task_threads or task_red:
            fixes.append(_Fix(task, max(task["prs"]), task_threads, task_red))
    return fixes


def _next_task_section(item: dict, delivery: list[dict], chosen: dict, comments: list[dict]) -> str:
    slug = item_branch_slug(item)
    branch = task_branch_name(slug, chosen["taskId"])
    predecessor = after_predecessor(delivery, chosen)
    lines = [
        "## Next Task",
        "",
        f"### {chosen['title']}",
        f"number: {chosen['number']}",
        f"taskId: {chosen['taskId']}",
        f"isUI: {'true' if chosen['isUI'] else 'false'}",
        f"branch: {branch}",
    ]
    if predecessor and not predecessor.complete and predecessor.pr is None:
        lines += [
            "",
            f"blocked: this worktree stacks after work item {predecessor.ref}, which has no implemented "
            "task with a registered pull request yet.",
        ]
        return "\n".join(lines)

    if chosen["implementationInvalidated"]:
        invalidation = _latest_invalidation(chosen, comments)
        when = f" on {timeline_formatted_at(invalidation['createdAt'])}" if invalidation and invalidation.get("createdAt") else ""
        lines.append(
            f"reconcile: implementation invalidated{when} — re-read the task body and plan against the "
            "invalidation below before implementing"
        )
        if invalidation is not None:
            lines += ["", "#### Invalidation", evidence_comment_text(invalidation).strip()]

    lines += [
        "",
        f"Next: Run `pdlc inspect task {chosen['number']}` for the task body, acceptance criteria, technical "
        f"plan, and the implementer sub-agent under `## Agent`, then `pdlc checkout {chosen['number']}` and "
        "dispatch that sub-agent to implement the task on the checked-out branch.",
    ]
    return "\n".join(lines)


def _next_fix_section(item: dict, fix: _Fix, decisions: list[ChangeRequest]) -> str:
    task = fix.task
    number = task["number"]
    lines = [
        "## Next Fix",
        "",
        f"### {task['title']}",
        f"number: {number}",
        f"taskId: {task['taskId']}",
        f"pr: {fix.pr}",
        f"branch: {task_branch_name(item_branch_slug(item), task['taskId'])}",
        f"state: {task['state']}",
        "",
        f"This task is already implemented and its current changes are published in PR #{fix.pr}. "
        f"Run `pdlc checkout {number}` to put the working tree on that PR's branch; every fix below lands "
        "as a new commit on top of it, after the implementer has investigated the current implementation.",
    ]
    if fix.threads:
        lines += ["", f"#### Unresolved threads ({len(fix.threads)})"]
        for thread in fix.threads:
            where = f" on {thread['path']}:{thread['line']}" if thread.get("path") else ""
            lines.append(f"- @{thread['author']}{where} — {thread['body']} ({thread['url']})")
    if fix.red:
        lines += ["", f"#### Failing checks ({len(fix.red)})"]
        for pr in fix.red:
            lines.append(f"- PR #{pr['number']}: {pr.get('checks')} ({pr['url']})")
    if decisions:
        # A thread escalated to the driver stays unresolved on the host, so
        # this unit comes round again once the decision is answered; the answer
        # rides with the unit so the fix can apply it rather than escalate twice.
        lines += [
            "",
            f"#### Decisions ({len(decisions)})",
            "The driver has answered these decisions since the stage last published. A thread named in them "
            "that is still unresolved is approved for implementation: fix it per the answer, not escalate it "
            "again. One the driver resolved on the host is no longer listed above.",
        ]
        for request in decisions:
            comment = request.comment
            when = timeline_formatted_at(comment["createdAt"]) if comment.get("createdAt") else "undated"
            url = f" ({comment['url']})" if comment.get("url") else ""
            lines += ["", f"##### Decision resolution — {when}{url}", _nested(evidence_comment_text(comment), 3)]
    lines += [
        "",
        f"Next: Run `pdlc inspect task {number}` for the implementer sub-agent under `## Agent`, then "
        "dispatch that sub-agent to fix every thread and failing check above on the checked-out branch.",
    ]
    return "\n".join(lines)


def _open_requests_section(item: dict, delivery: list[dict], requests: list[ChangeRequest]) -> str:
    implemented = sorted((t for t in delivery if t.get("prs")), key=_stack_order)
    lines = [
        "## Open Requests",
        "",
        "Every delivery task is already implemented and published in the PR stack below; these requests ask "
        "for changes to that implemented work. Run `pdlc checkout NUMBER` with the top task's number to put "
        "the working tree on the top branch with every task branch of the stack local. Each fix lands as a "
        "new commit on the branch of the task it belongs to, lowest first; a fix with no clear owner, or one "
        "that needs a lower fix to build on, goes on the top branch. These requests stay listed until the "
        "stage publishes, so this unit is offered again until then.",
    ]
    for request in requests:
        comment = request.comment
        when = timeline_formatted_at(comment["createdAt"]) if comment.get("createdAt") else "undated"
        url = f" ({comment['url']})" if comment.get("url") else ""
        lines += ["", f"### {SOURCE_LABELS[request.source]} — {when}{url}", _nested(evidence_comment_text(comment))]
    lines += ["", "#### Stack"]
    for index, task in enumerate(implemented):
        top = ", top" if index == len(implemented) - 1 else ""
        lines.append(f"- {task['title']} (number {task['number']}, PR #{max(task['prs'])}{top})")
    if not implemented:
        lines.append("- no implemented task has a registered pull request")
    lines += [
        "",
        "Next: Run `pdlc inspect task NUMBER` for each task in the stack for its technical plan, and for the "
        "top task's implementer sub-agent under `## Agent`; then dispatch that sub-agent once with every "
        "request above and the stack, to place and fix each finding on its owning task's branch.",
    ]
    return "\n".join(lines)


def _nested(body: str, depth: int = 2) -> str:
    """A request body quoted under a `###` (or deeper) heading: its own headings
    drop `depth` levels so they never read as this command's `##` sections."""
    prefix = "#" * depth
    return "\n".join(f"{prefix}{line}" if line.startswith("#") else line for line in body.strip().splitlines())


def _checks_section(pull_requests: list[dict]) -> str:
    lines = ["## Checks", ""]
    for pr in pull_requests:
        lines.append(f"- PR #{pr['number']}: {check_state(pr.get('checks'))}")
    if not pull_requests:
        lines.append("- no registered pull request")
    return "\n".join(lines)


def inspect(issue: str) -> str:
    item, tasks, comments = record_snapshot(issue)
    delivery = [t for t in tasks if t.get("taskId")]
    ready, message = _readiness(item, delivery)
    attachments = attachments_markdown(attachments_for_item(item))
    if not ready:
        return "\n".join(["## Readiness", "", message, "", attachments]) + "\n"

    gate = item_gate(item)
    unit: str | None = None
    publish: str
    checks: str | None = None
    number = item["content"]["number"]

    eligible = sorted((t for t in delivery if _eligible(t)), key=_stack_order)
    unplanned = [t for t in delivery if t["state"] == "OPEN" and not t["hasPlan"]]
    if gate in ("Pending", "Stale") and eligible:
        mode = "implement"
        chosen = eligible[0]
        unit = _next_task_section(item, delivery, chosen, comments)
        publish = (
            f"After the task is implemented and its files are committed, run `pdlc post implement-task "
            f"{chosen['number']} SUMMARY` to record the implementation, open the task's PR, and close the task."
        )
    elif gate in ("Pending", "Stale") and unplanned:
        mode = "none"
        names = ", ".join(t["title"] for t in sorted(unplanned, key=lambda t: t["number"]))
        unit = f"## Next Task\n\nNone. {names} has no technical plan yet."
        publish = "Nothing to publish yet."
    else:
        # From here on the routing is one function of live host state, the
        # same whatever gate brought the record here.
        pull_requests = record_pull_requests(issue, record=item, tasks=delivery)
        threads = record_open_review_comments(issue, record=item, tasks=delivery)
        fixes = _fixes(delivery, pull_requests, threads)
        requests = [
            request
            for request in open_change_requests(comments, pipeline_for_item(item), "Implementation").requests
            if request.source in _TRIAGE_SOURCES
        ]
        if fixes:
            mode = "rework"
            fix = fixes[0]
            unit = _next_fix_section(item, fix, [r for r in requests if r.source == "resolution"])
            publish = (
                "After every thread and failing check above is fixed and the files are committed, run "
                f"`pdlc post implement-task {fix.task['number']} SUMMARY` to re-land the fix on the task's PR; "
                "the task stays closed."
            )
        elif requests:
            mode = "triage"
            unit = _open_requests_section(item, delivery, requests)
            publish = (
                f"After every fix is committed on its task branch, run `pdlc post implement {number} EVIDENCE` "
                "from the top branch to push the whole stack and publish the stage; the evidence names how each "
                "request was addressed."
            )
        else:
            mode = "none"
            checks = _checks_section(pull_requests)
            unit = "## Next Task\n\nNone. Every delivery task is closed. Continue the workflow with the command under `## Publish`."
            publish = f"Run `pdlc post implement {number} EVIDENCE` to publish the stage at Review Required."

    sections = ["## Readiness", "", message, "", "## Mode", "", f"mode: {mode}", "", attachments]
    if checks is not None:
        sections += ["", checks]
    sections += ["", unit, "", "## Publish", "", publish]
    return "\n".join(sections) + "\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Resolve the Implementation mode and the one unit to work next")
    parser.add_argument("work_item")
    args = parser.parse_args(command_args)

    try:
        output = inspect(args.work_item)
    except PdlcError as error:
        return report_failure(error)

    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
