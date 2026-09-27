#!/usr/bin/env python3
"""NAME
    pdlc prompt tech-planner - write the technical planner's brief for a record's open delivery tasks; nothing is published to the backend

USAGE
    - when starting the stage's planning:
      pdlc prompt tech-planner WORK_ITEM [--follow-up FILE|text:BODY]
    - when revising the task files of an earlier pass, such as a reviewed one:
      pdlc prompt tech-planner WORK_ITEM --current-plan-manifest-path FILE [--follow-up FILE|text:BODY]

DESCRIPTION
    Writes the complete brief for the sub-agent that spikes a record's open
    delivery tasks against current source and writes an implementation-ready
    plan for each. It prints only the brief file's path; that file is sent to
    that sub-agent verbatim.

    It refuses, printing the reason and writing nothing, whenever the record's
    `Status` is not `Technical Plan`, and when no delivery task is open and
    unimplemented. Every open, unimplemented task gets its own file in the
    work-item cache, lowest in the stack first: its full body between
    `--- BEGIN TASK ---` and `--- END TASK ---`, then its existing
    `## Technical Plan` text, or a placeholder comment when it has none,
    between `--- BEGIN TECH PLAN ---` and `--- END TECH PLAN ---`. A manifest
    names every file with its task's id, number, and title, and a baseline of
    the recorded body and plan; `pdlc post plan` takes that manifest. The brief
    names the manifest and each file with its task's plan status, read from
    the file against the recorded plan: `no plan yet` when the plan block is
    empty or still the placeholder, `planned` when it matches the recorded
    plan, and `drafted, not yet landed` when it holds a plan the record does
    not; it does not embed their bodies. The planner edits only the plan blocks,
    so a reconciling pass edits what it would overwrite in place. The brief
    also carries every change request the stage has received since it last
    published, read off the record; with none, that section is omitted.

    `--current-plan-manifest-path` names the manifest of an earlier pass to keep
    revising instead of generating fresh files, such as the one a reviewer saw.
    A new planning pass begins either way, so the record of the files last
    handed to the plan reviewer is cleared. If any of those files changed
    since, the command first restores each to the reviewed version, keeps the
    edited copy beside it as `<name>.rejected.md`, and refuses so the review is
    redone.

    `--follow-up` carries the driver's verbatim request, or a reviewer's
    findings to send back to the planner; with nothing given, or a findings
    file still holding its unfilled outline, that section is omitted.

FLAGS
    --current-plan-manifest-path FILE  an earlier pass's plan manifest to revise instead of fresh files
    --follow-up FILE|text:BODY  the driver's verbatim follow-up for this pass

EXAMPLES
    pdlc prompt tech-planner 236
    pdlc prompt tech-planner 236 --follow-up text:"re-spike TASK-003 against the tile cache"
    pdlc prompt tech-planner 236 --current-plan-manifest-path /tmp/plan.json --follow-up /tmp/findings.md
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
    parser.add_argument("--current-plan-manifest-path", metavar="FILE", help="an earlier pass's plan manifest to revise")
    args = parser.parse_args(command_args)

    return prompt.run(
        COMMAND,
        args,
        lambda: prompt.tech_planner_brief(args.work_item, args.follow_up, args.current_plan_manifest_path),
    )


if __name__ == "__main__":
    raise SystemExit(main())
