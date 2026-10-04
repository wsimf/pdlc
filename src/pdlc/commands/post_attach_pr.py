#!/usr/bin/env python3
"""NAME
    pdlc post attach-pr - attach a pull request to a delivery task by hand

USAGE
    pdlc post attach-pr DELIVERY_TASK PR

DESCRIPTION
    Records PR on the delivery task's pull-request list. Idempotent. PR is a
    bare number or `#123` for a pull request in the configured code
    repository, or `owner/name#123` for one in another repository.

This is the list later stages read for a task's pull requests, rather than
inferring them from a `Closes #N` keyword or a branch name. `pdlc post
implement-task` registers the task's PR for you; reach for this only to
attach a PR it did not create or to repair a missing link. DELIVERY_TASK
must be a work item with WORK-NNN-TASK-NNN identity.

`prs` lists every pull request now on the task: a number for one in the
configured code repository, `owner/name#N` for one in another.

    {"task": 47, "prs": [148, "acme/web#12"]}
"""

from __future__ import annotations

import argparse
import json
import sys

from pdlc.config import get_config
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.records import PullRef
from pdlc.internal.pull_requests import prs_json
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.workitem import attach_pr, tasks_by_number
from pdlc.internal.failure import Recovery, report_failure, set_recovery


def post_attach_pr(delivery_task: str, pr: str) -> dict:
    if not delivery_task.isdigit():
        raise PdlcError(f"delivery task number must be numeric: {delivery_task}")
    ref = PullRef.parse(pr, get_config().pull_request_repository())

    task = tasks_by_number([delivery_task])[0]
    if task.get("taskId") is None:
        raise PdlcError(f"work item #{delivery_task} is not a delivery task (no WORK-NNN-TASK-NNN identity)")

    return {"task": int(delivery_task), "prs": prs_json(attach_pr(delivery_task, ref))}


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw_args = command_args
    if wants_help(raw_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Attach a pull request to a delivery task")
    parser.add_argument("delivery_task", help="Delivery task number")
    parser.add_argument("pr", help="Pull request: N, #N, or owner/name#N")
    args = parser.parse_args(raw_args)

    try:
        set_recovery(Recovery(
            check=f"pdlc inspect task {args.delivery_task}",
            landed=f"pull request {args.pr} is registered on the task",
        ))
        result = post_attach_pr(args.delivery_task, args.pr)
    except PdlcError as error:
        return report_failure(error)

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
