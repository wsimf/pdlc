#!/usr/bin/env python3
"""NAME
    pdlc post implement - register the current branch's PR and complete Implementation

USAGE
    pdlc post implement WORK_ITEM EVIDENCE_FILE|text:STR|- [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --attachment PATH (repeatable)      attach a local file's contents to the evidence comment
    --attachment-description TEXT       description for the --attachment immediately before it

DESCRIPTION
    Publish every task branch of the current stack, register the top task pull
    request for the current branch, and complete the Implementation stage.

The current branch must be the top task branch of the implementation stack.
The command syncs and pushes that stack itself, so commits made on any task
branch since its last land — a triage fix, for instance — reach their pull
requests with every base still chained; no skill or sub-agent pushes a task
branch by hand. The push runs after the record has been validated for the
transition and before anything is marked ready or posted: a failed push leaves
the record and the pull requests untouched, while a failure after it is safe to
re-run.

The PR number is recorded on the record — later stages read the record's pull
requests from that registry, not from a `Closes #N` keyword in the PR body.
"""

from __future__ import annotations

import json
import sys


from pdlc.hosts.code_host import get_code_host
from pdlc.internal.complete_transition import complete_transition, prepare_transition
from pdlc.internal.attachments import parse_attachment_arguments
from pdlc.internal.workitem import attach_pr
from pdlc.internal.pull_requests import record_pull_requests
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help


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
        code_host = get_code_host()
        # The stack mechanism owns bases and rebases, so any commit left on a
        # task branch is published through it rather than a bare `git push`.
        code_host.submit_task_stack()
        pull_request = code_host.ensure_pull_request_linked(issue)
        attach_pr(issue, pull_request["number"])
        # Every task PR was opened as a draft while the stack was still being
        # built; the whole implementation is now claimed done, so take the open
        # ones out of draft together for human review. Done before the evidence
        # posts so a failure here leaves the record cleanly republishable.
        open_prs = [pr["number"] for pr in record_pull_requests(issue) if pr["state"] == "OPEN"]
        code_host.mark_pull_requests_ready(open_prs)
        result = complete_transition(publication, evidence, attachment_inputs)
        result["pullRequest"] = pull_request
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
