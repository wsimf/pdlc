#!/usr/bin/env python3
"""Register the top task pull request for the current branch, then complete the
Implementation stage.

    pdlc post implement WORK_ITEM EVIDENCE_FILE|- [--attachment PATH [--attachment-description TEXT]]

The PR number is recorded on the record — later stages read the record's pull
requests from that registry, not from a `Closes #N` keyword in the PR body.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


from pdlc.hosts.code_host import get_code_host  # type: ignore
from pdlc.internal.complete_transition import complete_transition, prepare_transition  # type: ignore
from pdlc.internal.attachments import parse_attachment_arguments  # type: ignore
from pdlc.internal.workitem import register_record_pr  # type: ignore
from pdlc.domain.lifecycle import PdlcError, print_help, wants_help  # type: ignore


def main() -> int:
    raw_args = sys.argv[1:]
    if wants_help(raw_args):
        print_help(__doc__)
        return 0
    try:
        args, attachment_inputs = parse_attachment_arguments(raw_args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    if len(args) != 2:
        print("usage: pdlc post implement WORK_ITEM EVIDENCE_FILE|-", file=sys.stderr)
        return 1

    issue, evidence = args
    try:
        publication = prepare_transition(issue, "Implementation")
        pull_request = get_code_host().ensure_pull_request_linked(issue)
        register_record_pr(issue, pull_request["number"])
        result = complete_transition(publication, evidence, attachment_inputs)
        result["pullRequest"] = pull_request
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
