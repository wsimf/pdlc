#!/usr/bin/env python3
"""NAME
    pdlc prompt tasks-reviewer - print the reviewer's brief for a UI fragment or Tasks breakdown; nothing is published to the backend

USAGE
    pdlc prompt tasks-reviewer WORK_ITEM (--manifest FILE | --fragment FILE|text:BODY) [--findings FILE|text:BODY] [--file]

DESCRIPTION
    Prints the complete brief for the reviewer checking a UI fragment or
    Tasks breakdown before it is posted to the work item store. The output is
    sent to that sub-agent verbatim.

    Exactly one of `--manifest` or `--fragment` is required: `--manifest`
    names the Tasks-stage manifest `pdlc post tasks --stage Tasks` takes; the
    brief lists each entry's body file path rather than inlining it, except a
    removed task's stored body, which has no file of its own and is inlined.
    `--fragment` names the UI section's content for the UI stage; the brief
    names its file path rather than inlining it, and a `text:` fragment is
    first written to the work-item cache so it has a path too. The parent's
    complete body is always inlined, so the reviewer can check every cited
    `FR-*`/`C-*`/`UJ-*` without a second read; for a fragment review, the
    parent's own `## UI` section is left out, since the fragment replaces it.

    For a `--manifest` review, the command records the exact manifest and task
    body files it hands the reviewer in the work-item cache, and
    `pdlc post tasks --stage Tasks` lands only those files unchanged. If a file
    recorded by an earlier review changed since, the command first restores
    each to the reviewed version, keeps the edited copy beside it as
    `<name>.rejected.<ext>`, and refuses so that review is discarded and redone.

    `--findings` carries the previous pass's findings on a re-review, so each
    can be confirmed addressed; with nothing given, the brief has no prior
    findings section.

FLAGS
    --manifest FILE              a Tasks-stage manifest; mutually exclusive with --fragment
    --fragment FILE|text:BODY    the proposed UI section; mutually exclusive with --manifest
    --findings FILE|text:BODY    the previous pass's findings, on a re-review
    --file                       write the brief to
                                 the work-item cache with a random filename
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
