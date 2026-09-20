#!/usr/bin/env python3
"""NAME
    pdlc inspect task - read-only: render one or more delivery tasks in full

USAGE
    pdlc inspect task DELIVERY_TASK [DELIVERY_TASK ...] [--file]

FLAGS
    --file    write the rendered markdown to a temp file and print its path, instead of stdout

DESCRIPTION
    Renders one or more delivery tasks, each as its own
    YAML front-matter block (number, title, url, state, taskId, isUI, hasPlan,
    hasImplementation, implementationInvalidated, needsPlan) followed by its
    full body as a `# Task` markdown section — pdlc inspect's shape, but for
    whichever tasks a caller actually needs in full, rather than every task on
    the record.

    `hasPlan` reflects that this task has a `## Technical Plan` comment; `needsPlan`
    tracks that directly. `hasImplementation` reflects that a pull request is
    attached to the task — it survives invalidation, since invalidation only
    deletes evidence comments, not the PR. `implementationInvalidated` is true when
    a PR is attached but the task's `## Implementation` comment is missing, i.e.
    reopened for rework since it was last implemented — by a driver
    invalidation, or by a re-landed breakdown that changed this task's own body.
    Read `pdlc inspect task timeline` for which. When the task has a plan,
    it is rendered after the `# Task` body. Read these flags and the rendered plan
    rather than fetching task comments directly.

    Pair this with `pdlc inspect WORK_ITEM`, whose default output is a compact
    index: read it first to shortlist which task numbers are worth fetching in
    full, then pass those numbers here. Use `pdlc inspect --full` when the full
    work item body is needed inline.

    Each task ends with an `## Agent` section naming the implementer sub-agent the
    project routes that task to, resolved from its own `isUI` against the `[agents]`
    capability slots (`ui-implementer` / `core-implementer`, both falling back to
    `general-purpose`). It is a routing fact, not an instruction to dispatch — only
    `pdlc-implement` acts on it.

    The parent Work Item's local attachments are rendered once, between the first
    task's front matter and its `# Task` body. Each task then carries its own
    `## User Comments` — the comments on that task that carry no `PDLC-*` marker and
    do not open with the task's `## Technical Plan` / `## Implementation` evidence
    headings, i.e. human discussion only; the plan and implementation render through
    their own sections below. Parent-level discussion lives in
    `pdlc inspect WORK_ITEM`, not here.

    --file writes the rendered markdown to {TEMPDIR}/{repo}-task-{numbers}.md
    instead of stdout, and prints that path — for callers (e.g. subagent
    prompts) that want a file reference rather than inline content.

        ---
        number: 45
        title: "WORK-42-TASK-001 [CORE] Add foo"
        url: "..."
        state: OPEN
        taskId: TASK-001
        isUI: false
        hasPlan: true
        hasImplementation: false
        implementationInvalidated: false
        needsPlan: false
        ---

        ## Attachments

        ...the parent Work Item's attachments, on the first task only...

        ## User Comments

        ...this task's own unmarked comments, or "None"...

        # Task

        ...raw markdown...

        ## Technical Plan

        ...the task's plan, when it has one...

        ## Agent

        my-ui-implementer — the project's implementer for a [UI] task.
"""

from __future__ import annotations

import argparse
import sys


from pdlc.config import get_capabilities
from pdlc.internal.attachments import attachments_for_item, attachments_markdown, parent_number_for_task
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import TASK_EVIDENCE_HEADINGS, user_comments_markdown
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.reporting import older_comments_notice, yaml_front_matter
from pdlc.internal.scratch import scratch_path, write_scratch
from pdlc.internal.workitem import resolve_item, tasks_by_number


# The implementer slot a task's own `isUI` routes to. Resolved here, on the task,
# because the routing is per task rather than per record; `pdlc inspect capability`
# performs the same lookup for callers holding no task.
def _agent_section(task: dict) -> str:
    slot = "ui-implementer" if task["isUI"] else "core-implementer"
    phase = "[UI]" if task["isUI"] else "[CORE]"
    agent = get_capabilities().agent(slot)
    return f"## Agent\n\n{agent} — the project's implementer for a {phase} task."


# `preamble` is the parent Work Item's attachment section, rendered once on the
# first task between its front matter and body. Each task then carries its own
# `## User Comments` (its unmarked comments, minus the unmarked plan/implementation
# evidence comments), matching `pdlc inspect`'s front-matter -> attachments -> user
# comments -> body order but scoped to the task rather than the parent.
def _render_task(task: dict, preamble: str = "") -> str:
    front_matter = yaml_front_matter({
        "number": task["number"],
        "title": task["title"],
        "url": task["url"],
        "state": task["state"],
        "taskId": task["taskId"],
        "isUI": task["isUI"],
        "hasPlan": task["hasPlan"],
        "hasImplementation": task["hasImplementation"],
        "implementationInvalidated": task["implementationInvalidated"],
        "needsPlan": task["needsPlan"],
        "prs": task["prs"],
    })
    body = (task.get("body") or "").rstrip("\n")
    # The plan and implementation comments are unmarked; render them through
    # their own sections below, not as user discussion.
    comments = user_comments_markdown(
        task.get("commentObjects") or [], exclude_headings=TASK_EVIDENCE_HEADINGS
    )
    sections = [front_matter, *([preamble] if preamble else []), comments, f"# Task\n\n{body}"]
    rendered = "\n\n".join(sections)
    notice = older_comments_notice(task["number"], task.get("commentsMeta"), len(task.get("comments") or []))
    if notice:
        rendered += f"\n\n> Older comments are omitted from this view. {notice}."
    plan = (task.get("planComment") or "").strip()
    if plan:
        rendered += f"\n\n{plan}"
    return f"{rendered}\n\n{_agent_section(task)}"


def render(numbers: list[str]) -> str:
    tasks = tasks_by_number(numbers)
    parent_numbers = {parent_number_for_task(task) for task in tasks}
    if len(parent_numbers) != 1:
        raise PdlcError("delivery tasks must belong to the same Work Item")
    parent = next(iter(parent_numbers))
    attachments = attachments_for_item(resolve_item(parent))
    preamble = attachments_markdown(attachments)
    rendered = [_render_task(task, preamble if index == 0 else "") for index, task in enumerate(tasks)]
    return "\n\n".join(rendered) + "\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("numbers", nargs="+", metavar="DELIVERY_TASK")
    parser.add_argument(
        "--file", action="store_true",
        help="write to {TEMPDIR}/{repo}-task-{numbers}.md and print that path instead of stdout",
    )
    args = parser.parse_args(command_args)

    try:
        output = render(args.numbers)
        if args.file:
            suffix = "-".join(args.numbers)
            print(write_scratch(scratch_path(f"task-{suffix}"), output))
        else:
            sys.stdout.write(output)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
