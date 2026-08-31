#!/usr/bin/env python3
"""Attach a pull request to a delivery task by hand.

    pdlc post attach-pr DELIVERY_TASK PR_NUMBER

Records PR_NUMBER (a bare number or `#123`) in the delivery task's machine-owned
metadata block — the list later stages read to know a task's pull requests
explicitly, never inferring them from a `Closes #N` keyword or a branch name.
Idempotent.

On the stacked-PR path `pdlc post implement-task` registers the task's PR for
you; reach for this only to attach a PR it did not create or to repair a missing
link. DELIVERY_TASK must be a work item with WORK-NNN-TASK-NNN identity.

    {"task": 47, "prs": [148]}
"""

from __future__ import annotations

import argparse
import json
import sys

from pdlc.domain.lifecycle import PdlcError, print_help, wants_help  # type: ignore
from pdlc.internal.workitem import register_task_pr, tasks_by_number  # type: ignore


def post_attach_pr(delivery_task: str, pr_number: str) -> dict:
    if not delivery_task.isdigit():
        raise PdlcError(f"delivery task number must be numeric: {delivery_task}")
    number = pr_number.lstrip("#")
    if not number.isdigit():
        raise PdlcError(f"pull request number must be numeric: {pr_number}")

    task = tasks_by_number([delivery_task])[0]
    if task.get("taskId") is None:
        raise PdlcError(f"work item #{delivery_task} is not a delivery task (no WORK-NNN-TASK-NNN identity)")

    prs = register_task_pr(delivery_task, int(number))
    return {"task": int(delivery_task), "prs": prs}


def main() -> int:
    raw_args = sys.argv[1:]
    if wants_help(raw_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Attach a pull request to a delivery task")
    parser.add_argument("delivery_task", help="Delivery task number")
    parser.add_argument("pr_number", help="Pull request number")
    args = parser.parse_args(raw_args)

    try:
        result = post_attach_pr(args.delivery_task, args.pr_number)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
