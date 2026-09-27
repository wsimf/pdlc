#!/usr/bin/env python3
"""NAME
    pdlc prompt product-reviewer - read-only: write the reviewer's brief for a Product draft

USAGE
    pdlc prompt product-reviewer DRAFT [--work-item WORK_ITEM] [--findings FILE|text:BODY]

DESCRIPTION
    Writes the complete brief for the reviewer checking a Product draft before
    it is posted to the work item store. It prints only the brief file's path;
    that file is sent to that sub-agent verbatim.

    Unlike the other `prompt` briefs, which resolve a unit already on a
    record, the draft this describes may exist only as a local scratch file,
    so it takes the draft's own path as `DRAFT` rather than resolving one from
    a work item, and the reviewer reads that file itself instead of receiving
    its contents inlined.

    `--work-item` carries the record being reconciled, when there is one; a
    fresh draft with no record yet renders "none, new record" in its place.
    `--findings` carries the previous pass's findings on a re-review, so each
    can be confirmed addressed; with nothing given, that section renders
    "none, first review".

FLAGS
    --work-item WORK_ITEM       the record being reconciled, when reconciling
    --findings FILE|text:BODY   the previous pass's findings, on a re-review

EXAMPLES
    pdlc prompt product-reviewer /tmp/pdlc-route-shape-detection-body.md
    pdlc prompt product-reviewer /tmp/pdlc-route-shape-detection-body.md --work-item 236
    pdlc prompt product-reviewer /tmp/draft.md --findings text:"tighten FR-2"
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "product-reviewer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the reviewer's brief for a Product draft")
    parser.add_argument("draft", help="the draft file's path")
    parser.add_argument("--work-item", help="the record being reconciled")
    parser.add_argument("--findings", help="the previous pass's findings (FILE or text:BODY)")
    prompt.add_inline_argument(parser)
    args = parser.parse_args(command_args)

    work_item = args.work_item
    args.work_item = work_item or "new"  # only the scratch filename ever sees this default

    return prompt.run(COMMAND, args, lambda: prompt.product_reviewer_brief(args.draft, work_item, args.findings))


if __name__ == "__main__":
    raise SystemExit(main())
