#!/usr/bin/env python3
"""NAME
    pdlc prompt tech-planner - read-only: print the technical planner's brief for a record's open delivery tasks

USAGE
    pdlc prompt tech-planner WORK_ITEM [--follow-up FILE|text:BODY] [--file]

DESCRIPTION
    Prints the complete brief for the sub-agent that spikes a record's open
    delivery tasks against current source and returns an implementation-ready
    plan for each. The output is sent to that sub-agent verbatim.

    It refuses, printing the reason and writing nothing, whenever the record's
    `Status` is not `Technical Plan`, and when no delivery task is open and
    unimplemented. Every open, unimplemented task is carried, lowest in the
    stack first, with its full body, whether it still needs a plan, and its
    existing `## Technical Plan` text, so a reconciling pass sees what it would
    overwrite. The brief also carries every change request the stage has
    received since it last published, read off the record; with none, that
    section is omitted.

    `--follow-up` carries the driver's verbatim request, or a reviewer's
    findings to send back to the planner; with nothing given, that section is
    omitted.

FLAGS
    --follow-up FILE|text:BODY  the driver's verbatim follow-up for this pass
    --file                  write the brief to
                            the work-item cache with a random filename
                            and print that path, instead of stdout

EXAMPLES
    pdlc prompt tech-planner 236
    pdlc prompt tech-planner 236 --follow-up text:"re-spike TASK-003 against the tile cache"
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "tech-planner"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the technical planner's brief for a record's open delivery tasks")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--follow-up", help="the driver's verbatim follow-up (FILE or text:BODY)")
    args = parser.parse_args(command_args)

    return prompt.run(
        COMMAND,
        args,
        lambda: prompt.tech_planner_brief(args.work_item, args.follow_up),
    )


if __name__ == "__main__":
    raise SystemExit(main())
