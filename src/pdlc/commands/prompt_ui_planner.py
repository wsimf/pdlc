#!/usr/bin/env python3
"""NAME
    pdlc prompt ui-planner - read-only: print the UI planner's brief for a record's UI section

USAGE
    pdlc prompt ui-planner WORK_ITEM [--file]
    - when revising a prior UI fragment:
      pdlc prompt ui-planner WORK_ITEM --current-journeys-path FILE --follow-up FILE|text:BODY [--file]

DESCRIPTION
    Prints the complete brief for the sub-agent that authors a record's `UI`
    section. The output is sent to that sub-agent verbatim.

    It refuses, printing the reason and writing nothing, whenever the record's
    `Status` is not `UI`. The brief opens with the project's configured
    UX-design skill line, so the agent knows whether to invoke one before
    resolving any experience decision. It carries the record's `Gate State`,
    any recorded stale reason, every open change request the UI stage has
    received since it last published, and its existing delivery-task tree, if
    any.

    When the record already has a `UI` section, the command writes it to the
    work-item cache as an editable fragment and the brief names that file; the
    embedded parent body then omits the section, so the fragment is its only
    copy.

    A rework brief names the previous UI fragment, used instead of the
    published section, and carries the driver's verbatim follow-up. The two
    inputs must be supplied together.

FLAGS
    --current-journeys-path FILE  existing UI fragment; required with --follow-up
    --follow-up FILE|text:BODY    the driver's verbatim follow-up; requires --current-journeys-path
    --file                  write the brief to
                            the work-item cache with a random filename
                            and print that path, instead of stdout

EXAMPLES
    pdlc prompt ui-planner 236
    pdlc prompt ui-planner 236 --current-journeys-path /tmp/pdlc-ui.md --follow-up /tmp/findings.md
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
    parser.add_argument("--current-journeys-path", metavar="FILE", help="the existing UI fragment for a rework pass")
    args = parser.parse_args(command_args)

    return prompt.run(
        COMMAND,
        args,
        lambda: prompt.ui_planner_brief(
            args.work_item, args.follow_up, args.current_journeys_path
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
