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
  reads every registered pull request's checks: all settled prints the stage
  publish under `## Publish`; any still pending says to wait. With unplanned
  tasks left, the record is waiting on planning instead.

A pull request whose checks are pending or running is never a unit and never
holds the loop: the next unit proceeds while it runs, and `mode: none` settles
it at the end. Review threads and check state are live host state, read fresh
each call, not evidence PDLC recorded; nothing here resolves a thread or
judges a request.

`## Judgment Required` lists what the caller must still confirm for this mode's
unit — dependency closure by Result and HITL approval for a task, ownership and
driver-level calls for a fix or a request. `## Attachments` lists the record's
attachments. The unit section (`## Next Task`, `## Next Fix`, or `## Open
Requests`) ends with a `Next:` sentence naming the one read-only hop before
doing the work; `## Publish` is always last and holds the one mutating command
that lands the unit or the stage.

`## Next Task` names the task with its `branch:` and whatever setup lines the
configured code host needs to put that branch on its stack. For GitHub, the
setup lines are `gh stack` invocations entered at the previous implemented
task's registered pull request. For the first task of a worktree prepared with
`pdlc prepare --after`, the predecessor work item's latest implemented task PR
is reported as `stackAfter:` and `stackSetup:` tells the caller to implement
directly on the worktree's current branch instead. A predecessor with no such
PR yet blocks the task, and a Complete one falls back to a fresh stack. A code
host with no stacked-PR mechanism contributes no setup line. `pdlc checkout`
performs that same move for a task, so these lines are here to read rather than
to run by hand. A Stale task also carries a `reconcile:` line and its
`#### Invalidation` comment in full.

Not ready, or nothing to do, is reported plainly rather than raised.

    ## Readiness

    Ready — Gate State: Changes Required.

    ## Mode

    mode: rework

    ## Judgment Required

    - a thread or finding that turns on a product, architecture, UX, safety,
      or scope call is the driver's; report it and leave the thread open

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
    branch; every fix below lands as a new commit on top of it.

    #### Unresolved threads (1)
    - @reviewer on src/chart.py:42 — this drops the retry (https://.../#discussion_r1)

    Next: Run `pdlc inspect task 49` for the implementer agent, then fix every
    thread and failing check above on the checked-out branch.

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
from pdlc.hosts.code_host import get_code_host
from pdlc.internal.attachments import attachments_for_item, attachments_markdown
from pdlc.internal.ci_gate import check_state
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.pull_requests import record_open_review_comments, record_pull_requests
from pdlc.internal.stack import after_predecessor, stack_entry_pr, task_branch_name
from pdlc.internal.workitem import due_next, item_slug, pipeline_for_item, record_snapshot

# The change-request sources whose text is the whole record's, not one task's:
# they cannot be attributed to a pull request, so they form the triage unit.
_TRIAGE_SOURCES = ("review", "bounce", "resolution")

_DRIVER_CALL = "a thread or finding that turns on a product, architecture, UX, safety, or scope call is the driver's; report it and leave the thread open"

_JUDGMENT = {
    "implement": [
        "every task this one depends on is closed, proven by its Result and current source — not its state alone",
        "if this task is HITL, the driver's approval for it is recorded on the record",
    ],
    "rework": [_DRIVER_CALL],
    "triage": [
        "give each request an owning task; a cross-cutting one goes on the top task",
        "a request already met by current source needs no fix; say so in the evidence",
        "a request that needs a product, architecture, UX, safety, or scope call is the driver's; report it and stop",
    ],
    "none": [],
}


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
    slug = item_slug(item)
    branch = task_branch_name(slug, chosen["taskId"])
    entry_pr = stack_entry_pr(delivery, chosen)
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
    if predecessor and not predecessor.complete:
        if predecessor.pr is None:
            lines += [
                "",
                f"blocked: this worktree stacks after work item {predecessor.ref}, which has no implemented "
                "task with a registered pull request yet.",
            ]
            return "\n".join(lines)
        # This worktree's own branch already sits on the predecessor's latest
        # task, and that branch may be checked out in the predecessor's own,
        # still-active worktree — `gh stack checkout` cannot claim it here. The
        # task is implemented directly on the current branch; `pdlc post
        # implement-task` links it onto the predecessor's stack at submit time.
        lines += [
            "stackSetup: none — stay on this worktree's current branch and implement "
            "directly here; do not create or check out the `branch` above yourself. "
            "`pdlc post implement-task` renames the current branch to it and links it "
            "onto the predecessor's stack when this task is submitted",
            f"stackAfter: {predecessor.ref}  (this worktree's predecessor work item; entry is its latest task PR {predecessor.pr})",
        ]
    else:
        # The stack is the code host's mechanism, so the setup lines come from
        # it — this only supplies the branch and the entry point PDLC owns.
        lines += get_code_host().task_stack_setup(branch, entry_pr)

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
        f"plan, and the implementer agent, then `pdlc checkout {chosen['number']}` and implement it on that branch.",
    ]
    return "\n".join(lines)


def _next_fix_section(item: dict, fix: _Fix) -> str:
    task = fix.task
    number = task["number"]
    lines = [
        "## Next Fix",
        "",
        f"### {task['title']}",
        f"number: {number}",
        f"taskId: {task['taskId']}",
        f"pr: {fix.pr}",
        f"branch: {task_branch_name(item_slug(item), task['taskId'])}",
        f"state: {task['state']}",
        "",
        f"This task is already implemented and its current changes are published in PR #{fix.pr}. "
        f"Run `pdlc checkout {number}` to put the working tree on that PR's branch; every fix below lands "
        "as a new commit on top of it.",
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
    lines += [
        "",
        f"Next: Run `pdlc inspect task {number}` for the implementer agent, then fix every thread and "
        "failing check above on the checked-out branch.",
    ]
    return "\n".join(lines)


def _open_requests_section(item: dict, delivery: list[dict], requests: list[ChangeRequest]) -> str:
    implemented = sorted((t for t in delivery if t.get("prs")), key=_stack_order)
    lines = [
        "## Open Requests",
        "",
        "Every delivery task is already implemented and published in the PR stack below; these requests ask "
        "for changes to that implemented work. Run `pdlc checkout NUMBER` with the owning task's number to put "
        "the working tree on that task's PR branch, fix there, and land it as a new commit on top. Work lowest "
        "in the stack first, since re-landing a task rebases every branch above it.",
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
        "Next: Split the requests above into findings and give each an owning task from the stack. For each "
        "owning task, run `pdlc inspect task NUMBER` for its implementer agent, check out its branch, and fix "
        "its findings there.",
    ]
    return "\n".join(lines)


def _nested(body: str) -> str:
    """A request body quoted under its `###` heading: its own headings drop two
    levels so they never read as this command's `##` sections."""
    return "\n".join(f"##{line}" if line.startswith("#") else line for line in body.strip().splitlines())


def _checks_section(pull_requests: list[dict]) -> str:
    lines = ["## Checks", ""]
    for pr in pull_requests:
        lines.append(f"- PR #{pr['number']}: {check_state(pr.get('checks'))}")
    if not pull_requests:
        lines.append("- no registered pull request")
    return "\n".join(lines)


def _judgment_section(mode: str) -> str:
    lines = _JUDGMENT[mode]
    return "## Judgment Required\n\n" + ("\n".join(f"- {line}" for line in lines) if lines else "None")


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
            unit = _next_fix_section(item, fix)
            publish = (
                "After every thread and failing check above is fixed and the files are committed, run "
                f"`pdlc post implement-task {fix.task['number']} SUMMARY` to re-land the fix on the task's PR; "
                "the task stays closed."
            )
        elif requests:
            mode = "triage"
            unit = _open_requests_section(item, delivery, requests)
            publish = (
                "After each owning task's fix is committed, run `pdlc post implement-task NUMBER SUMMARY` to "
                f"re-land it. Once every request is handled, run `pdlc post implement {number} EVIDENCE` to "
                "publish the stage; the evidence names how each request was addressed."
            )
        else:
            mode = "none"
            checks = _checks_section(pull_requests)
            if any(check_state(pr.get("checks")) == "pending" for pr in pull_requests):
                unit = f"## Next Task\n\nNone. Wait for the pending checks, then re-run `pdlc inspect implement {number}`."
                publish = "Nothing to publish while checks are pending."
            else:
                unit = "## Next Task\n\nNone. Every delivery task is closed and all checks are settled."
                publish = f"Run `pdlc post implement {number} EVIDENCE` to publish the stage at Review Required."

    sections = ["## Readiness", "", message, "", "## Mode", "", f"mode: {mode}", "", _judgment_section(mode), "", attachments]
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
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
