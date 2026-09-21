#!/usr/bin/env python3
"""NAME
    pdlc prompt task-planner - read-only: print the task planner's brief for a record's delivery-task breakdown

USAGE
    pdlc prompt task-planner WORK_ITEM [--follow-up FILE|text:BODY] [--file]

DESCRIPTION
    Prints the complete brief for the sub-agent that decomposes a record into a
    dependency-ordered set of delivery tasks. The output is sent to that
    sub-agent verbatim.

    It refuses, printing the reason and writing nothing, whenever the record's
    `Status` is not `Tasks`. The existing task tree, if any, is carried
    verbatim as each task's front matter — `completed`, `hasPlan`,
    `hasImplementation` — so a re-authoring pass reconciles against it rather
    than rewriting from scratch. At `Gate State: Stale`, the brief also carries
    why: every change request the stage has received since it last published,
    read off the record.

    `--follow-up` carries the driver's verbatim request on a re-authoring pass;
    with nothing given, the brief reads "none".

FLAGS
    --follow-up FILE|text:BODY  the driver's verbatim follow-up for this pass
    --file                  write the brief to
                            {TEMPDIR}/{repo}-prompt-task-planner-{work item}.md
                            and print that path, instead of stdout

EXAMPLES
    pdlc prompt task-planner 236
    pdlc prompt task-planner 236 --follow-up text:"split the export task in two"
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "task-planner"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the task planner's brief for a record's delivery-task breakdown")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--follow-up", help="the driver's verbatim follow-up (FILE or text:BODY)")
    args = parser.parse_args(command_args)

    return prompt.run(
        COMMAND,
        args,
        lambda: prompt.task_planner_brief(args.work_item, args.follow_up),
    )


if __name__ == "__main__":
    raise SystemExit(main())
