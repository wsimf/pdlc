#!/usr/bin/env python3
"""NAME
    pdlc prompt patch-reviewer - read-only: print PDLC's patch reviewer brief for a correction to a landed artifact

USAGE
    - if the corrected artifact is Product or UI:
        pdlc prompt patch-reviewer WORK_ITEM --stage Product|UI --body FILE [--file]
    - if the corrected artifact is Tasks:
        pdlc prompt patch-reviewer WORK_ITEM --stage Tasks --manifest FILE [--file]

DESCRIPTION
    Prints the complete brief for the reviewer judging whether a reviewed
    correction to one landed planning artifact affects any artifact built on
    top of it. The output is sent to the built-in general-purpose agent
    verbatim; the brief is the whole reviewer, so no sub-agent declaration or
    capability slot stands behind it.

    The draft is the same input the corrected stage's landing command takes.
    The brief inlines it, the record's landed body, and every delivery task's
    body, and names the stages between the corrected one and the active one;
    the reviewer's report opens with an `Earliest affected stage:` line that
    `pdlc post write --patch` and `pdlc post tasks --patch` read as --impact.

    Refused when the record's active stage may not patch --stage, and when no
    stage lies between them, since no impact report is needed then.

    This command is internal to the patch flow in `pdlc guide patch` and is
    deliberately absent from `pdlc --help` and the `pdlc prompt` index.

FLAGS
    --stage Product|UI|Tasks    required; the stage whose landed artifact is corrected
    --body FILE                 the corrected Product body or UI fragment; with --stage Product or UI
    --manifest FILE             the corrected Tasks manifest; with --stage Tasks
    --file                      write the brief to
                                {TEMPDIR}/{repo}-prompt-patch-reviewer-{work item}.md
                                and print that path, instead of stdout

EXAMPLES
    pdlc prompt patch-reviewer 236 --stage Product --body /tmp/pdlc-product.md --file
    pdlc prompt patch-reviewer 236 --stage Tasks --manifest /tmp/pdlc-tasks.json --file
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "patch-reviewer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print PDLC's patch reviewer brief")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--stage", required=True, choices=["Product", "UI", "Tasks"])
    parser.add_argument("--body", help="the corrected Product body or UI fragment")
    parser.add_argument("--manifest", help="the corrected Tasks manifest")
    args = parser.parse_args(command_args)

    return prompt.run(COMMAND, args, lambda: prompt.patch_reviewer_brief(args.work_item, args.stage, args.body, args.manifest))


if __name__ == "__main__":
    raise SystemExit(main())
