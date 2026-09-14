#!/usr/bin/env python3
"""NAME
    pdlc inspect implement - read-only: whether Implementation is due and the next task to implement

USAGE
    pdlc inspect implement WORK_ITEM [--task TASK-NNN | N] [--phase core|ui]

FLAGS
    --task TASK-NNN|N    restrict the scan to one delivery task
    --phase core|ui      restrict the scan to the CORE or UI half; cannot combine with --task

DESCRIPTION
    Resolves whether Implementation is due for a record and, if so, the single
    next delivery task to implement.

`## Readiness` reports whether the stage is due (Status Implementation, gate
Pending / Changes Required / Stale, not skipped). `## Next Task` names the first
eligible task in scope — OPEN, technically planned, not yet implemented — in
CORE-before-UI then task-number order, with its `branch:` and whatever setup
lines the configured code host needs to put that branch on its stack — its
`## Technical Plan` is not rendered here; the `pdlc inspect task` handoff below
renders it. For GitHub, the setup lines are `gh stack` invocations entered at the
previous implemented task's registered pull request. The stack vocabulary is the
host's own: nothing here computes a base branch or checks whether a
predecessor's branch still exists. A code host with no stacked-PR mechanism
contributes no setup line and the branch is the caller's to create.
`## Judgment Required` lists what the skill must still
confirm from the task body and record comments (dependency closure by Result,
HITL approval) — this script stops short of that judgment, exactly as
`pdlc inspect test` does. `## Remaining` summarises the rest. Whenever a task was
chosen, the output ends with the `pdlc inspect task` call that renders it in
full — its body, acceptance criteria, its `## Technical Plan`, and the `## Agent`
naming the implementer sub-agent it routes to.

Not ready, or nothing eligible, is reported plainly rather than raised.

    ## Readiness

    Ready — Gate State: Pending.

    ## Next Task

    ### WORK-142-TASK-004 [UI] Route profile chart
    number: 51
    taskId: TASK-004
    isUI: true
    branch: pdlc/record-142/task-004
    stackSetup: gh stack checkout 151 && gh stack add pdlc/record-142/task-004
    stackEntryPr: 151  (the previous implemented task's registered PR)

    ## Judgment Required

    - every task this one depends on is closed, proven by its Result and current
      source — not its state alone
    - if this task is HITL, the driver's approval for it is recorded on the record

    ## Remaining

    - WORK-142-TASK-005 [UI] ... (OPEN): not yet planned
    3 of 5 delivery tasks closed.

    Next: run `pdlc inspect task 51` for this task's full body, acceptance
    criteria, its `## Technical Plan`, and the sub-agent to implement it with.
"""

from __future__ import annotations

import argparse
import sys

from pdlc.internal.attachments import attachments_for_item, attachments_markdown
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help
from pdlc.hosts.code_host import get_code_host
from pdlc.internal.stack import stack_entry_pr, task_branch_name
from pdlc.internal.workitem import due_next, item_slug, resolve_item, task_tree

_PHASES = {"core": False, "ui": True}

_JUDGMENT = (
    "## Judgment Required\n\n"
    "The skill must still confirm from the task body and the record's comments:\n"
    "- every task this one depends on is closed, proven by its Result and current "
    "source — not its state alone\n"
    "- if this task is HITL, the driver's approval for it is recorded on the record"
)


def _normalise_task_filter(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if value.isdigit():
        return f"TASK-{int(value):03d}"
    return value.upper()


def _readiness(item: dict) -> tuple[bool, str]:
    status = item.get("Status")
    gate = item.get("Gate State")
    if status != "Implementation":
        return False, f"Not ready: Status is {status!r}, not Implementation. That stage owns this Work Item now."
    due = due_next(item)
    if due["action"] != "pdlc-implement":
        return False, f"Not ready: Gate State is {gate!r}. {due['reason'].capitalize()}."
    return True, f"Ready — Gate State: {gate}."


def _in_scope(task: dict, task_filter: str | None, phase: bool | None) -> bool:
    if task_filter is not None:
        return (task.get("taskId") or "").upper() == task_filter
    if phase is not None:
        return task["isUI"] == phase
    return True


def _eligible(task: dict) -> bool:
    return (
        task["state"] == "OPEN"
        and task["hasPlan"]
        and (not task["hasImplementation"] or task["implementationInvalidated"])
    )


def _remaining_status(task: dict) -> str:
    if task["hasImplementation"] and task["implementationInvalidated"]:
        return "implementation invalidated — eligible for rework"
    if task["hasImplementation"]:
        return "implementation recorded but task still open — report it"
    if not task["hasPlan"]:
        return "not yet planned"
    return "planned, eligible — later in order"


def _remaining_section(delivery: list[dict], chosen: dict | None, closed: int) -> str:
    others = [t for t in delivery if t["state"] == "OPEN" and (chosen is None or t["number"] != chosen["number"])]
    lines = ["## Remaining", ""]
    for task in sorted(others, key=lambda t: t["number"]):
        lines.append(f"- {task['title']} (OPEN): {_remaining_status(task)}")
    if not others:
        lines.append("- no other open delivery tasks")
    lines.append("")
    lines.append(f"{closed} of {len(delivery)} delivery tasks closed.")
    return "\n".join(lines)


def _next_task_section(item: dict, delivery: list[dict], task_filter: str | None, phase: bool | None) -> tuple[str, dict | None]:
    scoped = [t for t in delivery if _in_scope(t, task_filter, phase)]
    eligible = sorted((t for t in scoped if _eligible(t)), key=lambda t: (t["isUI"], t["number"]))

    if not eligible:
        if task_filter is not None:
            reason = f"no OPEN, planned, not-yet-implemented task matches {task_filter}"
        elif phase is not None:
            reason = f"no eligible {'UI' if phase else 'CORE'} task"
        elif not scoped:
            reason = "the record has no delivery tasks"
        else:
            reason = "no task is OPEN, planned, and not yet implemented"
        return f"## Next Task\n\n{reason}.", None

    chosen = eligible[0]
    slug = item_slug(item)
    branch = task_branch_name(slug, chosen["taskId"])
    # The stack is the code host's mechanism, so the setup lines come from it —
    # this only supplies the branch and the entry point PDLC itself owns.
    setup = get_code_host().task_stack_setup(branch, stack_entry_pr(delivery, chosen))

    # The `## Technical Plan` is not rendered here: the handoff line below routes
    # to `pdlc inspect task`, which renders it in full alongside the task body.
    lines = [
        "## Next Task",
        "",
        f"### {chosen['title']}",
        f"number: {chosen['number']}",
        f"taskId: {chosen['taskId']}",
        f"isUI: {'true' if chosen['isUI'] else 'false'}",
        f"branch: {branch}",
        *setup,
    ]
    return "\n".join(lines), chosen


def inspect(issue: str, task_filter: str | None, phase: bool | None) -> str:
    item = resolve_item(issue)
    ready, message = _readiness(item)
    attachments = attachments_markdown(attachments_for_item(item))
    sections = ["## Readiness", "", message]
    if not ready:
        return "\n".join(sections + ["", attachments]) + "\n"

    delivery = [t for t in task_tree(issue) if t.get("taskId")]
    closed = sum(1 for t in delivery if t["state"] == "CLOSED")

    next_section, chosen = _next_task_section(item, delivery, task_filter, phase)
    sections += ["", attachments, "", next_section]
    if chosen is not None:
        sections += ["", _JUDGMENT]
    sections += ["", _remaining_section(delivery, chosen, closed)]
    if chosen is not None:
        # The handoff: everything needed to implement the task lives on the task
        # itself, including which sub-agent it routes to.
        sections += [
            "",
            f"Next: run `pdlc inspect task {chosen['number']}` for this task's full body, "
            "acceptance criteria, its `## Technical Plan`, and the sub-agent to implement it with.",
        ]
    return "\n".join(sections) + "\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw = command_args
    if wants_help(raw):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Resolve the next PDLC delivery task to implement")
    parser.add_argument("work_item")
    parser.add_argument("--task", help="Restrict to one delivery task (TASK-004 or 4)")
    parser.add_argument("--phase", choices=sorted(_PHASES), help="Restrict to the CORE or UI phase")
    args = parser.parse_args(raw)

    if args.task and args.phase:
        print("pdlc: --task and --phase cannot be combined", file=sys.stderr)
        return 1

    try:
        output = inspect(args.work_item, _normalise_task_filter(args.task), _PHASES.get(args.phase))
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
