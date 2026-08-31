#!/usr/bin/env python3
"""Read-only: renders one or more delivery tasks, each as its own
YAML front-matter block (number, title, url, state, taskId, isUI, hasPlan,
hasImplementation, needsPlan) followed by its full body as a `# Task` markdown
section — pdlc inspect's shape, but for whichever tasks a caller actually
needs in full, rather than every task on the record.

`hasPlan` reflects that this task has been technically planned; `hasImplementation`
reflects that implementation work has been carried out for it. When the task has
a plan, it is rendered after the `# Task` body. Read these flags and the rendered
plan rather than fetching task comments directly.

    pdlc inspect task DELIVERY_TASK [DELIVERY_TASK ...] [--file]

Pair this with `pdlc inspect WORK_ITEM`, whose default output is a compact
index: read it first to shortlist which task numbers are worth fetching in
full, then pass those numbers here. Use `pdlc inspect --full` when the full
work item body is needed inline.

The parent Work Item's local attachments and its `## User Comments` (comments
carrying no `PDLC-*` marker) are rendered once, between the first task's front
matter and its `# Task` body.

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
    needsPlan: false
    ---

    ## Attachments

    ...the parent Work Item's attachments, on the first task only...

    ## User Comments

    ...the parent Work Item's unmarked comments, on the first task only...

    # Task

    ...raw markdown...

    ## Technical Plan

    ...the task's plan, when it has one...
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


from pdlc.internal.attachments import attachments_for_item, attachments_markdown, parent_number_for_task  # type: ignore
from pdlc.domain.lifecycle import PdlcError  # type: ignore
from pdlc.internal.reporting import yaml_front_matter  # type: ignore
from pdlc.internal.workitem import ref_label, resolve_item, strip_task_meta, tasks_by_number, user_comments_markdown  # type: ignore


# `preamble` is the parent Work Item's attachment and user-comment sections: they
# sit between the first task's front matter and its `# Task` body, matching
# `pdlc inspect`'s front-matter -> attachments -> user comments -> body order.
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
        "needsPlan": task["needsPlan"],
        "prs": task["prs"],
    })
    body = strip_task_meta(task.get("body") or "").rstrip("\n")
    lead = f"{preamble}\n\n" if preamble else ""
    rendered = f"{front_matter}\n\n{lead}# Task\n\n{body}"
    plan = (task.get("planComment") or "").strip()
    if plan:
        rendered += f"\n\n{plan}"
    return rendered


def render(numbers: list[str]) -> str:
    tasks = tasks_by_number(numbers)
    parent_numbers = {parent_number_for_task(task) for task in tasks}
    if len(parent_numbers) != 1:
        raise PdlcError("delivery tasks must belong to the same Work Item")
    parent = next(iter(parent_numbers))
    attachments = attachments_for_item(resolve_item(parent))
    preamble = f"{attachments_markdown(attachments)}\n\n{user_comments_markdown(parent)}"
    rendered = [_render_task(task, preamble if index == 0 else "") for index, task in enumerate(tasks)]
    return "\n\n".join(rendered) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect one or more PDLC delivery tasks")
    parser.add_argument("numbers", nargs="+", metavar="DELIVERY_TASK")
    parser.add_argument(
        "--file", action="store_true",
        help="write to {TEMPDIR}/{repo}-task-{numbers}.md and print that path instead of stdout",
    )
    args = parser.parse_args()

    try:
        output = render(args.numbers)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    if args.file:
        suffix = "-".join(args.numbers)
        path = Path(tempfile.gettempdir()) / f"{ref_label()}-task-{suffix}.md"
        path.write_text(output)
        print(path)
    else:
        sys.stdout.write(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
