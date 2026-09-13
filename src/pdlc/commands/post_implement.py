#!/usr/bin/env python3
"""NAME
    pdlc post implement - register the current branch's PR and complete Implementation

USAGE
    pdlc post implement WORK_ITEM EVIDENCE_FILE|text:STR|- [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --attachment PATH (repeatable)      attach a local file's contents to the evidence comment
    --attachment-description TEXT       description for the --attachment immediately before it

DESCRIPTION
    Register the top task pull request for the current branch, then complete the
    Implementation stage.

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
