#!/usr/bin/env python3
"""NAME
    pdlc prompt task-planner - read-only: print the task planner's brief for a record's delivery-task breakdown

USAGE
    pdlc prompt task-planner WORK_ITEM [--file]
    - when revising a prior task breakdown:
      pdlc prompt task-planner WORK_ITEM --current-tasks-manifest-path FILE --follow-up FILE|text:BODY [--file]

DESCRIPTION
    Prints the complete brief for the sub-agent that decomposes a record into a
    dependency-ordered set of delivery tasks. The output is sent to that
    sub-agent verbatim.

    It refuses, printing the reason and writing nothing, whenever the record's
    `Status` is not `Tasks`. Every existing task is carried with its complete
    body and progress metadata, so a re-authoring pass can preserve unaffected
    tasks and rewrite only those the current work item or change inputs affect.
    The brief also carries every open change request the Tasks stage has
    received since it last published; with none, that section is omitted.

    `--follow-up` carries the driver's verbatim request on a re-authoring pass;
    with nothing given, that section is omitted. A rework pass also supplies
    the current task manifest, whose task body files the agent reads and revises.
    The two inputs must be supplied together.

FLAGS
    --current-tasks-manifest-path FILE  existing task manifest; required with --follow-up
    --follow-up FILE|text:BODY    the driver's verbatim follow-up; requires --current-tasks-manifest-path
    --file                  write the brief to
                            the work-item cache with a random filename
                            and print that path, instead of stdout

EXAMPLES
    pdlc prompt task-planner 236
    pdlc prompt task-planner 236 --current-tasks-manifest-path /tmp/tasks.json --follow-up text:"split the export task in two"
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
    parser.add_argument("--current-tasks-manifest-path", metavar="FILE", help="the existing task manifest for a rework pass")
    args = parser.parse_args(command_args)

    return prompt.run(
        COMMAND,
        args,
        lambda: prompt.task_planner_brief(
            args.work_item, args.follow_up, args.current_tasks_manifest_path
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
