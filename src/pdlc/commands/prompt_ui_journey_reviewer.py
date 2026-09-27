#!/usr/bin/env python3
"""NAME
    pdlc prompt ui-journey-reviewer - read-only: write the brief for the user-journey reviewer

USAGE
    pdlc prompt ui-journey-reviewer WORK_ITEM --description FILE|text:BODY

DESCRIPTION
    Writes the complete brief for the sub-agent that builds and runs the current
    worktree, then walks a record's due UI journeys and rendered UX. It prints
    only the brief file's path; that file is sent to that sub-agent verbatim.

    It refuses, printing the reason and writing nothing, whenever Verification
    is not due, the record carries no UI task, or every journey and UX are
    already carried forward from an earlier pass — the same carried-forward
    resolution `pdlc inspect verify` renders as its own `## Journeys to
    review` section, read here directly rather than re-derived. Each due
    journey's full `UJ-*` text is copied from the parent's `UI` section
    verbatim, and the UX-review step is included only when it needs a fresh
    pass.

    `--description` is a one-sentence account of what shipped, since the
    sub-agent knows nothing about PDLC and cannot resolve it from the record
    itself.

FLAGS
    --description FILE|text:BODY  one-sentence account of what shipped; required

EXAMPLES
    pdlc prompt ui-journey-reviewer 236 --description text:"offline route retry with backoff"
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "ui-journey-reviewer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the brief for the user-journey reviewer")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--description", required=True, help="one-sentence account of what shipped")
    args = parser.parse_args(command_args)

    return prompt.run(COMMAND, args, lambda: prompt.ui_journey_reviewer_brief(args.work_item, args.description))


if __name__ == "__main__":
    raise SystemExit(main())
