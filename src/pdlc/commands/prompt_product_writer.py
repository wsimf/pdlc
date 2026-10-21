#!/usr/bin/env python3
"""NAME
    pdlc prompt product-writer - write the Product author's brief and keep its draft; nothing is published to the backend

USAGE
    - if authoring a new work item that has no record yet:
        pdlc prompt product-writer --slug SLUG [--restart] [--attachment PATH [--attachment-description TEXT]]
    - if authoring or reconciling an existing record's Product, or one never authored:
        pdlc prompt product-writer --work-item WORK_ITEM [--restart] [--attachment PATH [--attachment-description TEXT]]
    - if the driver asked for a spec change while Product awaits their approval:
        pdlc prompt product-writer --work-item WORK_ITEM --reauthor [--restart] [--attachment PATH [--attachment-description TEXT]]
    - if correcting the landed Product while the record is at a later stage:
        pdlc prompt product-writer --work-item WORK_ITEM --patch [--restart] [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --slug SLUG               the new work item's kebab-case slug; fixed once the draft exists
    --work-item WORK_ITEM     the existing record whose Product is authored
    --reauthor                action="store_true"; revise a Product at Approval Required on the driver's request
    --patch                   action="store_true"; revise a landed Product from a later stage
    --restart                 action="store_true"; discard the draft, its reviews, and its attachments, then start again
    --attachment PATH (repeatable)      a local file the driver supplied, such as a mockup; recorded for the draft
    --attachment-description TEXT       description for the --attachment immediately before it

DESCRIPTION
    Writes the brief for the agent authoring a work item's Product with the
    driver, and keeps the Product draft that agent edits. It prints only the
    brief file's path. Unlike the sub-agent briefs, this one is read by the
    agent already talking with the driver, so it treats answers the driver has
    already given as settled.

    On first use the command creates the draft at a fixed path in the
    work-item cache, keyed by the work item number or, before a record exists,
    by `new-<slug>`. A new work item and a record never authored start from
    the `## Product`, `## Decisions`, and `## Open Questions` headings, and a
    record never authored has its description embedded as requirements; an
    existing record
    starts from its current Product-owned sections, with the change requests,
    upstream changes, and Stale reason that apply embedded verbatim. Every
    later run keeps the draft as it is, so the command is re-run after each
    step: it reads the draft, its review stamp, and both reviews' findings, and
    the brief's `## Where the draft stands` and `## Next steps` name the one
    step due next, with the exact command and paths:

    - draft the product sections, then the product review;
    - re-review after the product sections change, or fix or reject findings,
      answering each with an `Author response:` line;
    - the feasibility spike, once the product review is clean on the draft as
      it stands;
    - back to the driver when the spike finds the product not feasible, until
      it is;
    - the technical review of the whole draft, then its findings;
    - landing, once both reviews are clean on the draft as it stands.

    Any change to the product sections after a review or spike sends the draft
    back through it. The brief also lists what keeps the draft from landing as
    it stands once it carries a technical approach.

    Each --attachment is recorded for the draft and kept across runs, so a file
    is passed once; passing the same path again replaces its description. The
    brief lists the record's existing attachments and the recorded ones, the
    reviewer and spike briefs list the same files, and the land command the
    brief names carries every recorded --attachment. A recorded file that has
    since moved or emptied makes every brief on the draft refuse.

    It refuses, writing nothing, when the slug is not kebab-case or already
    names a record; when the record is at Product / Approval Required without
    --reauthor, or at Decision Required (see `pdlc guide decisions`); when it is
    past Product without --patch, or --patch finds it may not patch Product;
    and at any other gate.

EXAMPLES
    pdlc prompt product-writer --slug route-shape-detection
    pdlc prompt product-writer --work-item 236
    pdlc prompt product-writer --slug route-shape-detection --attachment mockup.png --attachment-description "Route sheet mockup"
    pdlc prompt product-writer --work-item 236 --reauthor
    pdlc prompt product-writer --work-item 236 --patch
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.attachments import parse_attachment_arguments
from pdlc.internal.failure import report_failure
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "product-writer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the Product author's brief")
    parser.add_argument("--slug")
    parser.add_argument("--work-item")
    parser.add_argument("--reauthor", action="store_true")
    parser.add_argument("--patch", action="store_true")
    parser.add_argument("--restart", action="store_true")
    prompt.add_inline_argument(parser)

    try:
        command_args, attachments = parse_attachment_arguments(command_args)
        args = parser.parse_args(command_args)
        brief, key = prompt.product_writer_brief(
            args.work_item, args.slug, args.reauthor, args.patch, args.restart, attachments,
        )
        prompt.emit(brief, key, COMMAND, args.inline)
    except PdlcError as error:
        return report_failure(error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
