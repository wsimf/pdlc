#!/usr/bin/env python3
"""NAME
    pdlc post attach-pr - attach a pull request to a delivery task by hand

USAGE
    pdlc post attach-pr DELIVERY_TASK PR_NUMBER

DESCRIPTION
    Records PR_NUMBER (a bare number or `#123`) on the delivery task's
    pull-request list. Idempotent.

This is the list later stages read for a task's pull requests, rather than
inferring them from a `Closes #N` keyword or a branch name. `pdlc post
implement-task` registers the task's PR for you; reach for this only to
attach a PR it did not create or to repair a missing link. DELIVERY_TASK
must be a work item with WORK-NNN-TASK-NNN identity.

    {"task": 47, "prs": [148]}
"""

from __future__ import annotations

import argparse
import json
import sys

from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.workitem import attach_pr, tasks_by_number
from pdlc.internal.failure import Recovery, report_failure, set_recovery


def post_attach_pr(delivery_task: str, pr_number: str) -> dict:
    if not delivery_task.isdigit():
        raise PdlcError(f"delivery task number must be numeric: {delivery_task}")
    number = pr_number.lstrip("#")
    if not number.isdigit():
        raise PdlcError(f"pull request number must be numeric: {pr_number}")

    task = tasks_by_number([delivery_task])[0]
    if task.get("taskId") is None:
        raise PdlcError(f"work item #{delivery_task} is not a delivery task (no WORK-NNN-TASK-NNN identity)")

    prs = attach_pr(delivery_task, int(number))
    return {"task": int(delivery_task), "prs": prs}


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw_args = command_args
    if wants_help(raw_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Attach a pull request to a delivery task")
    parser.add_argument("delivery_task", help="Delivery task number")
    parser.add_argument("pr_number", help="Pull request number")
    args = parser.parse_args(raw_args)

    try:
        set_recovery(Recovery(
            check=f"pdlc inspect task {args.delivery_task}",
            landed=f"pull request #{args.pr_number} is registered on the task",
        ))
        result = post_attach_pr(args.delivery_task, args.pr_number)
    except PdlcError as error:
        return report_failure(error)

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
