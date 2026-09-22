#!/usr/bin/env python3
"""NAME
    pdlc prompt tasks-reviewer - read-only: print the reviewer's brief for a UI fragment or Tasks breakdown

USAGE
    pdlc prompt tasks-reviewer WORK_ITEM (--manifest FILE | --fragment FILE|text:BODY) [--findings FILE|text:BODY] [--file]

DESCRIPTION
    Prints the complete brief for the reviewer checking a UI fragment or
    Tasks breakdown before it is posted to the work item store. The output is
    sent to that sub-agent verbatim.

    Exactly one of `--manifest` or `--fragment` is required: `--manifest`
    names the Tasks-stage manifest `pdlc post tasks --stage Tasks` takes,
    rendering every entry's full task body (or, for an `"unchanged": true`
    entry, a note that it carries forward untouched instead); `--fragment`
    carries the UI section's own content for the UI stage. The parent's
    complete body is always inlined, so the reviewer can check every cited
    `FR-*`/`C-*`/`UJ-*` without a second read.

    `--findings` carries the previous pass's findings on a re-review, so each
    can be confirmed addressed; with nothing given, that section renders
    "none, first review".

FLAGS
    --manifest FILE              a Tasks-stage manifest; mutually exclusive with --fragment
    --fragment FILE|text:BODY    a UI section's content; mutually exclusive with --manifest
    --findings FILE|text:BODY    the previous pass's findings, on a re-review
    --file                       write the brief to
                                 {TEMPDIR}/{repo}-prompt-tasks-reviewer-{work item}.md
                                 and print that path, instead of stdout

EXAMPLES
    pdlc prompt tasks-reviewer 236 --manifest /tmp/pdlc-tasks.json
    pdlc prompt tasks-reviewer 236 --fragment /tmp/pdlc-ui.md
    pdlc prompt tasks-reviewer 236 --manifest /tmp/pdlc-tasks.json --findings text:"tighten TASK-2"
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "tasks-reviewer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the reviewer's brief for a UI fragment or Tasks breakdown")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--manifest", help="a Tasks-stage manifest file")
    parser.add_argument("--fragment", help="a UI section's content (FILE or text:BODY)")
    parser.add_argument("--findings", help="the previous pass's findings (FILE or text:BODY)")
    args = parser.parse_args(command_args)

    return prompt.run(
        COMMAND, args,
        lambda: prompt.tasks_reviewer_brief(args.work_item, args.manifest, args.fragment, args.findings),
    )


if __name__ == "__main__":
    raise SystemExit(main())
