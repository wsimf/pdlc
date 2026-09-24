#!/usr/bin/env python3
"""NAME
    pdlc prompt task-implementer - read-only: print the implementer's brief for a work item's next unit

USAGE
    pdlc prompt task-implementer WORK_ITEM [--file]

DESCRIPTION
    Prints the complete brief for the sub-agent that writes the code of the unit
    a record has next, with every value already filled in. The output is sent to
    that sub-agent verbatim.

    The sub-agent to send it to is the one `pdlc inspect task` names under
    `## Agent`. Everything the brief interpolates is already on the record, so
    this command takes no artifacts of its own.

    The brief is chosen from the same unit the Implementation loop is on, so it
    always matches the work that is actually due:

    - a task to implement, or one whose implementation was invalidated, gets the
      implementation brief, with the invalidation carried as findings to address;
    - a task whose pull request has unresolved review threads gets the
      review-comment brief, carrying the driver's answers to anything escalated
      earlier, and the red checks on that pull request when it has them;
    - a task whose pull request is only failing its checks gets the
      implementation brief, with those checks as the findings to address;
    - open change requests against the stage get the triage brief, carrying every
      request and the whole task stack with each branch and plan.

FLAGS
    --file                  write the brief to
                            the work-item cache with a random filename
                            and print that path, instead of stdout

EXAMPLES
    pdlc prompt task-implementer 236
    pdlc prompt task-implementer 236 --file
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "task-implementer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the implementer's brief for a work item's next unit")
    prompt.add_common_arguments(parser, COMMAND)
    args = parser.parse_args(command_args)

    return prompt.run(COMMAND, args, lambda: prompt.implementer_brief(args.work_item))


if __name__ == "__main__":
    raise SystemExit(main())
