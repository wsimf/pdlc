#!/usr/bin/env python3
"""NAME
    pdlc post implement-task - land one delivery task's implementation on its pull request

USAGE
    pdlc post implement-task DELIVERY_TASK IMPLEMENTATION_FILE|text:STR|- [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --attachment PATH (repeatable)       attach a local file's contents to the implementation comment
    --attachment-description TEXT        description for the --attachment immediately before it
    --close                              accepted and ignored; closing is decided by the task's state

DESCRIPTION
    Lands one delivery task's implementation: submits its pull request, records
    the summary as the task's `## Implementation` comment and the PR
    description, and closes the task when it was open.

The task's own state decides what this is; there is no mode flag and the
record's gate is not consulted:

- if the task is OPEN (first implementation, or reopened after invalidation):
      the summary becomes its `## Implementation` comment and the task is closed.
      Run it once the task review passed, its unit coverage landed, and its
      criteria are met.
- if the task is CLOSED (a fix for a review thread, a red check, or a change
  request):
      the fix is re-landed: the existing `## Implementation` comment and the PR
      description are replaced by the summary, and the task stays closed. The
      JSON adds `relanded: true`, the PR's still-unresolved thread count as
      `openThreads`, and its check state as `checks`.

The implementation summary is a file path, or `text:<body>` for a short one,
and follows the template `pdlc template implementation-summary` prints. A
summary missing a required section, with an empty section, or with an
unfilled `- <placeholder>` bullet is refused before anything changes; the
error lists every problem and prints the template. On a re-land the summary
is the task's whole implementation, not just the fix. The
`## Implementation` heading is prepended
automatically when the summary does not already start with it; pdlc-inspect
reads that heading to report the task as implemented.

The implementation is recorded as its own artifact on the task, leaving the
human-authored task body and its Technical Plan as they were.

A task carries one `## Implementation` comment. Re-recording a task that
already has one edits the newest
in place and removes any older duplicates, so the comment always reads as what
finally shipped.

This first submits the task's stacked pull request via `gh stack` — or, for a
worktree's first task prepared with `pdlc prepare --after`, renames the current branch to its
deterministic name and links it onto the predecessor's stack instead, since
there is no local `gh stack` tracking to submit in that case. Either way this
then sets that PR's
title (the delivery task's own title with its `WORK-N-TASK-N` id prefix and
`[CORE]`/`[UI]` tag stripped, or the optional `[code_host] pr_title_format`
applied to it) and its body to this evidence (prefixed with the optional
`[code_host] pr_attachment` line, with `{work.number}` resolved to the parent
work item's bare number), and records its number on the task, then
writes the comment. The attachment line is PR-body only and never appears in the
`## Implementation` comment. A failure in that sequence
leaves no `## Implementation` comment and no closure, so `pdlc inspect implement`
still offers the task and a re-run is clean rather than a duplicate.

    {"commented": true, "task": 47, "mode": "implement", "closed": true,
     "attachments": [], "taskPr": {...}, "prs": [148]}

    {"commented": true, "task": 47, "mode": "rework", "closed": true,
     "relanded": true, "attachments": [], "taskPr": {...}, "prs": [148],
     "openThreads": 0, "checks": "pending"}
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from pdlc.config import get_config
from pdlc.hosts.code_host import get_code_host
from pdlc.internal.attachments import parent_number_for_task, parse_attachment_arguments, save_attachments
from pdlc.internal.ci_gate import check_state
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import decision_required_message
from pdlc.internal.inputs import print_help, require_file, wants_help
from pdlc.internal.stack import after_predecessor, task_branch_name
from pdlc.templates.template import require_template
from pdlc.internal.workitem import (
    IMPLEMENTATION_COMMENT_HEADING,
    close_task,
    delete_comment,
    edit_comment,
    heading_comment_objects,
    item_slug,
    post_comment,
    attach_pr,
    resolve_item,
    task_title,
    task_tree,
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

    The one exception is a worktree's first task prepared with `pdlc prepare
    --after` — there is no local `gh stack` tracking to sync/submit,
    since the predecessor's branch may live in another, still-active worktree
    and was never checked out here. That case renames the current branch to
    its deterministic name and links it onto the predecessor's stack instead.
    """
    parent = parent_number_for_task(task)
    slug = item_slug(resolve_item(parent))
    branch = task_branch_name(slug, task["taskId"])
    predecessor = after_predecessor(task_tree(parent), task)
    if predecessor and not predecessor.complete and predecessor.pr is not None:
        return get_code_host().link_task_stack(predecessor.pr, branch)
    prs = get_code_host().submit_task_stack()
    match = next((pr for pr in prs if pr["branch"] == branch), None)
    if match is None:
        submitted = ", ".join(pr["branch"] for pr in prs) or "none"
        raise PdlcError(
            f"the submitted stack has no pull request for {branch} "
            f"(branches submitted: {submitted}) — check the task branch is part of the stack"
        )
    return match


# Leading `[CORE]` / `[UI]` tag on a delivery task title (`tagged_title`), which
# carries no signal in a PR title — the UI/CORE distinction is machine-tracked on
# the task issue, not the PR.
_TASK_TAG = re.compile(r"^\[(?:CORE|UI)\]\s*")


def _pr_title(task: dict, work_number: str, work_type: str) -> str:
    """The task PR title: the delivery task's own title with its `WORK-N-TASK-N`
    id prefix and `[CORE]`/`[UI]` tag stripped, or the optional
    `[code_host] pr_title_format` applied to it. Placeholders: `{task.title}`
    (the stripped title), `{task.id}` (e.g. `TASK-001`), `{work.number}` (the
    parent's bare number), `{work.type}` (`feature`/`bug`).
    """
    bare = _TASK_TAG.sub("", task_title(task) or task["taskId"]).strip()
    template = (get_config().pr_title_format or "").strip()
    if not template:
        return bare
    return (
        template
        .replace("{task.title}", bare)
        .replace("{task.id}", task["taskId"])
        .replace("{work.number}", work_number)
        .replace("{work.type}", str(work_type))
    )


def _pr_body(summary: str, work_number: str) -> str:
    """The task PR description: the optional `[code_host] pr_attachment` line as
    the first line, then the implementation evidence. Every `{work.number}` in
    the attachment is replaced by the parent work item's bare number. Unset
    config leaves the body as the evidence alone, so the PR description then
    matches the `## Implementation` comment. The attachment never reaches the
    comment — it is a PR-body-only affordance.
    """
    attachment = (get_config().pr_attachment or "").strip()
    if not attachment:
        return summary
    return f"{attachment.replace('{work.number}', work_number)}\n\n{summary}"


def _record_implementation(delivery_task: str, comment_objects: list[dict], summary: str) -> None:
    """Keep one `## Implementation` comment on the task: edit the newest in
    place, then retire older duplicates newest-first; post only when there is
    none to edit. Readers take the newest match, so a failure part-way still
    leaves this summary authoritative."""
    existing = heading_comment_objects(comment_objects, IMPLEMENTATION_COMMENT_HEADING)
    if not existing or not existing[-1].get("url"):
        post_comment(delivery_task, summary)
        return
    *older, newest = existing
    edit_comment(delivery_task, newest["url"], summary)
    for comment in reversed(older):
        if comment.get("url"):
            delete_comment(delivery_task, comment["url"])


def post_implement_task(delivery_task: str, evidence: str, attachment_inputs: list[dict]) -> dict:
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
    if gate == "Decision Required":
        raise PdlcError(decision_required_message(status))
    if status != "Implementation" or due_next(parent).get("action") != "pdlc-implement":
        raise PdlcError(f"implementation is not active: parent is at {status} / {gate}")
    if not task.get("hasPlan"):
        raise PdlcError(f"{task['taskId']} has no Technical Plan and is not eligible for implementation")

    text = sys.stdin.read() if evidence == "-" else require_file("implementation file", evidence).read_text(encoding="utf-8")
    summary = text.strip()
    if not summary:
        raise PdlcError("the implementation summary is empty")
    require_template("implementation-summary", summary, "implementation summary")

    first = next((line.strip() for line in summary.splitlines() if line.strip()), "")
    if first != IMPLEMENTATION_COMMENT_HEADING:
        summary = f"{IMPLEMENTATION_COMMENT_HEADING}\n\n{summary}"

    attachments = save_attachments(parent_number_for_task(task), attachment_inputs)

    # An open task is being implemented and closes here; a closed one is
    # having a fix re-landed and stays closed. The task's state is the only
    # input — the record's gate never decides which.
    relanding = task["state"] == "CLOSED"
    result: dict = {
        "commented": True,
        "task": int(delivery_task),
        "mode": "rework" if relanding else "implement",
        "closed": True,
        "attachments": attachments,
    }
    if relanding:
        result["relanded"] = True
    # Submit and register the task PR before recording the implementation: a
    # stack-submit failure then leaves the task with no `## Implementation`
    # comment and no closure, so `pdlc inspect implement` still offers it and a
    # re-run is clean rather than a duplicate comment.
    task_pr = _submit_task_stack(task)
    # Give the freshly submitted PR its title (see `_pr_title`) and this evidence
    # as its description, replacing `gh stack`'s auto-generated summary. Runs before the
    # comment and closure so a failure here leaves the task re-runnable, exactly
    # like a stack-submit failure.
    get_code_host().set_pull_request_content(
        task_pr["number"],
        _pr_title(task, parent_number_for_task(task), pipeline.work_type),
        _pr_body(summary, parent_number_for_task(task)),
    )
    result["taskPr"] = task_pr
    result["prs"] = attach_pr(task["number"], task_pr["number"])

    _record_implementation(delivery_task, task.get("commentObjects") or [], summary)

    if relanding:
        # Read back what the next `pdlc inspect implement` will see, so the
        # caller knows whether this task will be offered again.
        result["openThreads"] = len(get_code_host().unresolved_review_comments(task_pr["number"]))
        result["checks"] = check_state(task_pr.get("checks"))
    else:
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
    parser.add_argument("evidence", help="Implementation comment body — a file path, or text:<body> for a short one")
    # Closing is decided by the task's state; the flag stays accepted so older
    # callers keep working, and does nothing.
    parser.add_argument("--close", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(script_args)

    try:
        result = post_implement_task(args.delivery_task, args.evidence, attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
