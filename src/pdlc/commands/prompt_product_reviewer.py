#!/usr/bin/env python3
"""NAME
    pdlc prompt product-reviewer - write the reviewer's brief for a Product draft; nothing is published to the backend

USAGE
    - if reviewing the product sections, before the feasibility spike:
        pdlc prompt product-reviewer DRAFT --pass product [--findings FILE|text:BODY]
    - if reviewing the whole draft once the spike wrote its technical approach:
        pdlc prompt product-reviewer DRAFT --pass technical [--findings FILE|text:BODY]

FLAGS
    --pass product|technical    which of the draft's two reviews this is
    --findings FILE|text:BODY   the previous pass's findings, each answered by the author, on a re-review

DESCRIPTION
    Writes the complete brief for the reviewer checking a Product draft before
    it is posted to the work item store. It prints only the brief file's path;
    that file is sent to that sub-agent verbatim.

    `DRAFT` is the draft `pdlc prompt product-writer` created; any other file
    is refused. The reviewer reads that file itself instead of receiving its
    contents inlined. When the draft revises an existing record, its current
    body is inlined under `Current record`.

    `--pass product` reviews every section except the `### Technical
    approach` subsection, and records the product content it hands over;
    `--pass technical` reviews the whole draft, checking the approach against
    the requirements, constraints, and current source, and records the whole
    draft. The technical pass is refused until the product review is clean on
    the draft as it stands and a feasibility spike wrote the approach against
    it. A product pass resets the technical review.

    Each pass writes a fresh findings outline to its own fixed path in the
    work-item cache, after reading `--findings`, and names it in the brief;
    the reviewer writes its findings and verdict there, so that file may be
    passed back as `--findings` on the re-review. Before a re-review, the
    author answers every prior finding with an `Author response: Fixed — ...`
    or `Author response: Rejected — ...` line under it; a `--findings` that
    leaves one unanswered is refused, naming its IDs. A `--findings` still
    holding the unfilled outline counts as no prior findings. A successful
    landing deletes both findings files.

EXAMPLES
    pdlc prompt product-reviewer .pdlc/cache/236/main-product-draft.md --pass product
    pdlc prompt product-reviewer .pdlc/cache/236/main-product-draft.md --pass technical --findings .pdlc/cache/236/main-technical-findings.md
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.failure import report_failure
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "product-reviewer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the reviewer's brief for a Product draft")
    parser.add_argument("draft", help="the Product draft's path")
    parser.add_argument("--pass", dest="review_pass", required=True, choices=("product", "technical"))
    parser.add_argument("--findings", help="the previous pass's findings (FILE or text:BODY)")
    prompt.add_inline_argument(parser)
    args = parser.parse_args(command_args)

    try:
        brief, key = prompt.product_reviewer_brief(args.draft, args.review_pass, args.findings)
        prompt.emit(brief, key, COMMAND, args.inline)
    except PdlcError as error:
        return report_failure(error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
