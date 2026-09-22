#!/usr/bin/env python3
"""NAME
    pdlc prompt ui-planner - read-only: print the UI planner's brief for a record's UI section

USAGE
    pdlc prompt ui-planner WORK_ITEM [--follow-up FILE|text:BODY] [--file]

DESCRIPTION
    Prints the complete brief for the sub-agent that authors a record's `UI`
    section. The output is sent to that sub-agent verbatim.

    It refuses, printing the reason and writing nothing, whenever the record's
    `Status` is not `UI`. The brief opens with the project's configured
    UX-design skill line, so the agent knows whether to invoke one before
    resolving any experience decision. It carries the record's `Gate State`,
    why it is `Stale` when it is (from the record-level invalidation naming
    `UI`, or that none is recorded), and its existing delivery-task tree, if
    any.

    `--follow-up` carries the driver's verbatim request on a reconciling pass;
    with nothing given, that section reads "none".

FLAGS
    --follow-up FILE|text:BODY  the driver's verbatim follow-up for this pass
    --file                  write the brief to
                            {TEMPDIR}/{repo}-prompt-ui-planner-{work item}.md
                            and print that path, instead of stdout

EXAMPLES
    pdlc prompt ui-planner 236
    pdlc prompt ui-planner 236 --follow-up text:"revisit UJ-2's offline flow"
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "ui-planner"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the UI planner's brief for a record's UI section")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--follow-up", help="the driver's verbatim follow-up (FILE or text:BODY)")
    args = parser.parse_args(command_args)

    return prompt.run(COMMAND, args, lambda: prompt.ui_planner_brief(args.work_item, args.follow_up))


if __name__ == "__main__":
    raise SystemExit(main())
