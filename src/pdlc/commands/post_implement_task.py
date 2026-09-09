#!/usr/bin/env python3
"""Records one delivery task's implementation as a `## Implementation` comment
on the delivery task, and optionally closes it — the two things Step 5 of
pdlc-implement does together, in one call.

    pdlc post implement-task DELIVERY_TASK IMPLEMENTATION_FILE|- [--close] [--attachment PATH [--attachment-description TEXT]]

IMPLEMENTATION_FILE is the summary body. Cover what shipped, the files touched,
which acceptance criteria the evidence establishes, the validation run, the
linked PR, and any limitation. The `## Implementation` heading is prepended
automatically when the summary does not already start with it; pdlc-inspect
reads that heading to report the task as implemented.

The implementation is recorded as its own artifact on the task, leaving the
human-authored task body and its Technical Plan as they were. Pass --close once
the task review passed, its unit coverage landed, and its criteria are met.

This first submits the task's stacked pull request via `gh stack`, sets that PR's
title to the delivery task's own title and its body to this evidence (plus the
optional `[code_host] pr_attachment` line, with `{work.number}` resolved to the
parent work item's bare number), and records its number on the task, then writes
the comment. A failure in that sequence
leaves no `## Implementation` comment and no closure, so `pdlc inspect implement`
still offers the task and a re-run is clean rather than a duplicate.

    {"commented": true, "task": 47, "closed": true, "attachments": [],
     "taskPr": {...}, "prs": [148]}
"""

from __future__ import annotations

import argparse
import json
import sys

from pdlc.config import get_config
from pdlc.hosts.code_host import get_code_host
from pdlc.internal.attachments import parent_number_for_task, parse_attachment_arguments, save_attachments
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, require_file, wants_help
from pdlc.internal.stack import task_branch_name
from pdlc.internal.workitem import (
    IMPLEMENTATION_COMMENT_HEADING,
    close_task,
    item_slug,
    post_comment,
    attach_pr,
    resolve_item,
    task_title,
    workflow_for_item,
    due_next,
    item_status,
    item_gate,
    tasks_by_number,
)


def _submit_task_stack(task: dict) -> dict:
    """Submit the stack this task's branch belongs to and return this task's
    pull request.

    The stack itself is `gh stack`'s: the skill built it with `gh stack
    init`/`add`, and the host submits it as-is. All this does is pick out the PR
    whose head is this task's branch.
    """
    slug = item_slug(resolve_item(parent_number_for_task(task)))
    branch = task_branch_name(slug, task["taskId"])
    prs = get_code_host().submit_task_stack()
    match = next((pr for pr in prs if pr["branch"] == branch), None)
    if match is None:
        submitted = ", ".join(pr["branch"] for pr in prs) or "none"
        raise PdlcError(
            f"the submitted stack has no pull request for {branch} "
            f"(branches submitted: {submitted}) — check the task branch is part of the stack"
        )
    return match


def _pr_body(summary: str, work_number: str) -> str:
    """The task PR description: the implementation evidence, plus the optional
    `[code_host] pr_attachment` line with every `{work.number}` replaced by the
    parent work item's bare number. Unset config leaves the body as the evidence
    alone, so the PR description matches the `## Implementation` comment.
    """
    attachment = (get_config().pr_attachment or "").strip()
    if not attachment:
        return summary
    return f"{summary}\n\n{attachment.replace('{work.number}', work_number)}"


def post_implement_task(delivery_task: str, evidence: str, close: bool, attachment_inputs: list[dict]) -> dict:
    if not delivery_task.isdigit():
        raise PdlcError(f"delivery task number must be numeric: {delivery_task}")

    try:
        task = tasks_by_number([delivery_task])[0]
    except (IndexError, KeyError) as error:
        raise PdlcError(f"no delivery task found for #{delivery_task}") from error
    if task.get("taskId") is None:
        raise PdlcError(f"work item #{delivery_task} is not a delivery task (no WORK-NNN-TASK-NNN identity)")

    parent = resolve_item(parent_number_for_task(task))
    pipeline, _ = workflow_for_item(parent)
    status = item_status(parent)
    gate = item_gate(parent)
    if status == pipeline.terminal_stage:
        raise PdlcError("the parent work item is Complete and locked")
    if status != "Implementation" or due_next(parent).get("action") != "pdlc-implement":
        raise PdlcError(f"implementation is not active: parent is at {status} / {gate}")
    if not task.get("hasPlan"):
        raise PdlcError(f"{task['taskId']} has no Technical Plan and is not eligible for implementation")

    text = sys.stdin.read() if evidence == "-" else require_file("implementation file", evidence).read_text(encoding="utf-8")
    summary = text.strip()
    if not summary:
        raise PdlcError("the implementation summary is empty")

    first = next((line.strip() for line in summary.splitlines() if line.strip()), "")
    if first != IMPLEMENTATION_COMMENT_HEADING:
        summary = f"{IMPLEMENTATION_COMMENT_HEADING}\n\n{summary}"

    attachments = save_attachments(parent_number_for_task(task), attachment_inputs)

    result = {"commented": True, "task": int(delivery_task), "closed": close, "attachments": attachments}
    # Submit and register the task PR before recording the implementation: a
    # stack-submit failure then leaves the task with no `## Implementation`
    # comment and no closure, so `pdlc inspect implement` still offers it and a
    # re-run is clean rather than a duplicate comment.
    task_pr = _submit_task_stack(task)
    # Give the freshly submitted PR the task's own title and this evidence as its
    # description, replacing `gh stack`'s auto-generated summary. Runs before the
    # comment and closure so a failure here leaves the task re-runnable, exactly
    # like a stack-submit failure.
    get_code_host().set_pull_request_content(
        task_pr["number"],
        task_title(task) or task["taskId"],
        _pr_body(summary, parent_number_for_task(task)),
    )
    result["taskPr"] = task_pr
    result["prs"] = attach_pr(task["number"], task_pr["number"])

    post_comment(delivery_task, summary)

    if close:
        close_task(delivery_task)

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

    parser = argparse.ArgumentParser(description="Record one delivery task's implementation comment")
    parser.add_argument("delivery_task", help="Delivery task number")
    parser.add_argument("evidence", help="Implementation comment body — a file path, or - for stdin")
    parser.add_argument("--close", action="store_true", help="Close the task after the comment lands")
    args = parser.parse_args(script_args)

    try:
        result = post_implement_task(args.delivery_task, args.evidence, args.close, attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
