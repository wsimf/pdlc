#!/usr/bin/env python3
"""Records one delivery task's implementation as a `## Implementation` comment
on the delivery task, and optionally closes it — the two things Step 5 of
pdlc-implement does together, in one call.

    pdlc-post-implement-task.py DELIVERY_TASK IMPLEMENTATION_FILE|- [--close] [--attachment PATH [--attachment-description TEXT]]

IMPLEMENTATION_FILE is the summary body. Cover what shipped, the files touched,
which acceptance criteria the evidence establishes, the validation run, the
linked PR, and any limitation. The `## Implementation` heading is prepended
automatically when the summary does not already start with it; pdlc-inspect
reads that heading to report the task as implemented.

The implementation is recorded as its own artifact on the task, leaving the
task body and its Technical Plan as they were. Pass --close to close the task
once the commit is pushed, the shared PR's checks are green, and the task's
criteria are genuinely met.

    {"commented": true, "task": 47, "closed": true}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


from pdlc.attachments import parent_number_for_task, parse_attachment_arguments, save_attachments  # type: ignore
from pdlc.pdlc_common import PdlcError, print_help, require_file, wants_help  # type: ignore
from pdlc.workitem import (  # type: ignore
    IMPLEMENTATION_COMMENT_HEADING,
    close_task,
    post_comment,
    tasks_by_number,
)


def post_implement_task(delivery_task: str, evidence: str, close: bool, attachment_inputs: list[dict]) -> dict:
    if not delivery_task.isdigit():
        raise PdlcError(f"delivery task number must be numeric: {delivery_task}")

    task = tasks_by_number([delivery_task])[0]
    if task.get("taskId") is None:
        raise PdlcError(f"work item #{delivery_task} is not a delivery task (no WORK-NNN-TASK-NNN identity)")

    text = sys.stdin.read() if evidence == "-" else require_file("implementation file", evidence).read_text()
    summary = text.strip()
    if not summary:
        raise PdlcError("the implementation summary is empty")

    first = next((line.strip() for line in summary.splitlines() if line.strip()), "")
    if first != IMPLEMENTATION_COMMENT_HEADING:
        summary = f"{IMPLEMENTATION_COMMENT_HEADING}\n\n{summary}"

    attachments = save_attachments(parent_number_for_task(task), attachment_inputs)
    post_comment(delivery_task, summary)

    if close:
        close_task(delivery_task)

    return {"commented": True, "task": int(delivery_task), "closed": close, "attachments": attachments}


def main() -> int:
    raw_args = sys.argv[1:]
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
