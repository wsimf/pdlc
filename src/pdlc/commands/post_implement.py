#!/usr/bin/env python3
"""NAME
    pdlc post implement - publish the delivery task pull request stack and complete Implementation

USAGE
    pdlc post implement WORK_ITEM EVIDENCE_FILE|text:STR|- [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --attachment PATH (repeatable)      attach a local file's contents to the evidence comment
    --attachment-description TEXT       description for the --attachment immediately before it

DESCRIPTION
    Publishes every task branch of the implementation stack, takes the stack's
    open pull requests out of draft, and completes the Implementation stage.

The command syncs and pushes the stack itself, so commits made on any task
branch since its last land — a triage fix, for instance — reach their pull
requests with every base still chained; no skill or sub-agent pushes a task
branch by hand. The push runs after the record has been validated for the
transition and before anything is marked ready or posted: a failed push leaves
the record and the pull requests untouched, while a failure after it is safe to
re-run.

Which pull requests belong to the record is read from the registry its delivery
tasks already carry, so no pull request is resolved from the working tree and it
does not matter which branch of the stack is checked out here.

After the push, the working tree is checked out on the top task's branch (the
highest-numbered implemented task), since Testing commits its coverage on the
current branch and needs every task's code under it. `checkedOut` names that
branch, or is null when no task has an implementation and a pull request yet.
The tree must be clean; a dirty tree fails here, before anything is posted.

    {"completed": true, "itemId": "PVTI_x", "work_item": 142,
     "stage": "Implementation", "gateState": "Review Required",
     "attachments": [], "checkedOut": "pdlc/record-142/task-004",
     "readyPullRequests": [{"number": 151, "url": "..."},
                           {"number": 153, "url": "..."}]}

`readyPullRequests` is every registered pull request this run took out of draft,
ascending — the stack a reviewer now has to read. An already-ready pull request
is listed again; a merged or closed one is not listed at all.
"""

from __future__ import annotations

import json
import sys


from pdlc.commands.checkout import check_out
from pdlc.hosts.code_host import get_code_host
from pdlc.internal.complete_transition import complete_transition, prepare_transition
from pdlc.internal.attachments import parse_attachment_arguments
from pdlc.internal.pull_requests import record_pull_requests
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, resolve_text, wants_help
from pdlc.internal.stack import latest_implemented_task, resolve_task_checkout
from pdlc.internal.workitem import task_tree


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw_args = command_args
    if wants_help(raw_args):
        print_help(__doc__)
        return 0
    try:
        args, attachment_inputs = parse_attachment_arguments(raw_args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    if len(args) != 2:
        print("usage: pdlc post implement WORK_ITEM EVIDENCE_FILE|text:STR|-", file=sys.stderr)
        return 1

    issue, evidence = args
    try:
        publication = prepare_transition(issue, "Implementation")
        evidence_body = resolve_text(evidence, label="evidence")
        code_host = get_code_host()
        # The stack mechanism owns bases and rebases, so any commit left on a
        # task branch is published through it rather than a bare `git push`.
        code_host.submit_task_stack()
        # Leave the tree on the top of the stack: Testing commits its coverage
        # on the current branch, and only the top branch holds every task. A
        # fix pass on a lower task would otherwise leave the tree down there.
        top = latest_implemented_task(task_tree(issue))
        top_checkout = resolve_task_checkout(top["title"]) if top else None
        if top_checkout:
            check_out(top_checkout)
        # Every task PR was opened as a draft while the stack was still being
        # built; the whole implementation is now claimed done, so take the open
        # ones out of draft together for human review. Done before the evidence
        # posts so a failure here leaves the record cleanly republishable.
        open_prs = [pr for pr in record_pull_requests(issue) if pr["state"] == "OPEN"]
        code_host.mark_pull_requests_ready([pr["number"] for pr in open_prs])
        result = complete_transition(publication, evidence_body, attachment_inputs)
        result["checkedOut"] = top_checkout.branch if top_checkout else None
        result["readyPullRequests"] = [{"number": pr["number"], "url": pr["url"]} for pr in open_prs]
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
