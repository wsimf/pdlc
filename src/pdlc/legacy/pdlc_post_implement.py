#!/usr/bin/env python3
"""Verify and link the implementation pull request, then complete the stage.

    pdlc-post-implement.py WORK_ITEM EVIDENCE_FILE|- [--attachment PATH [--attachment-description TEXT]]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


from pdlc.code_host import get_code_host  # type: ignore
from pdlc.complete_transition import complete_transition  # type: ignore
from pdlc.attachments import parse_attachment_arguments  # type: ignore
from pdlc.pdlc_common import PdlcError, print_help, wants_help  # type: ignore


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
        print("usage: pdlc-post-implement.py WORK_ITEM EVIDENCE_FILE|-", file=sys.stderr)
        return 1

    issue, evidence = args
    try:
        pull_request = get_code_host().ensure_pull_request_linked(issue)
        result = complete_transition(issue, evidence, "Implementation", attachment_inputs)
        result["pullRequest"] = pull_request
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
