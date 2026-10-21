#!/usr/bin/env python3
"""NAME
    pdlc prompt tech-feasibility - write the feasibility spike's brief for a reviewed Product draft; nothing is published to the backend

USAGE
    pdlc prompt tech-feasibility DRAFT [--findings FILE|text:BODY]

FLAGS
    --findings FILE|text:BODY   a technical review's findings, for a re-spike

DESCRIPTION
    Writes the complete brief for the sub-agent that spikes a Product draft
    against current source and writes its `### Technical approach`
    subsection. It prints only the brief file's path; that file is sent to
    that sub-agent verbatim.

    `DRAFT` is the draft `pdlc prompt product-writer` created; any other file
    is refused. The spike is due once the product review is clean on the draft
    as it stands, and the command refuses before then. The brief embeds the
    `technical-approach` template the subsection follows, and the current
    record when the draft revises one.

    The command records the product content it hands the spike, so a later
    change to it calls for a fresh spike, and resets the technical review,
    which must then review the new approach.

EXAMPLES
    pdlc prompt tech-feasibility .pdlc/cache/236/main-product-draft.md
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.failure import report_failure
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "tech-feasibility"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the feasibility spike's brief for a Product draft")
    parser.add_argument("draft", help="the Product draft's path")
    parser.add_argument("--findings", help="a technical review's findings (FILE or text:BODY)")
    prompt.add_inline_argument(parser)
    args = parser.parse_args(command_args)

    try:
        brief, key = prompt.tech_feasibility_brief(args.draft, args.findings)
        prompt.emit(brief, key, COMMAND, args.inline)
    except PdlcError as error:
        return report_failure(error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
