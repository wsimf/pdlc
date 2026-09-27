#!/usr/bin/env python3
"""NAME
    pdlc prompt task-reviewer - read-only: write the reviewer's brief for one dispatch's commits

USAGE
    pdlc prompt task-reviewer WORK_ITEM --commits REVISIONS

DESCRIPTION
    Writes the complete brief for the reviewer reading one dispatch's commits
    against the unit a record has next, with the task, its plan, and the diff
    already inlined. It prints only the brief file's path; that file is sent to
    that sub-agent verbatim.

    The reviewer reads a change that exists only in the working tree, so it takes
    the revisions to read. They are the caller's to pass because the range is one
    dispatch's, not the branch's: a second review pass, or a fix landing on top of
    implemented code, leaves the earlier commits on that same branch, so a range
    worked out from the branch would re-read work that was already reviewed.

    The reviewer is the project's configured reviewer agent, and the brief holds
    it to the same task, plan, and acceptance criteria the implementer was given
    on this pass.

FLAGS
    --commits REVISIONS     the revision or range the brief reads, as `git show`
                            accepts it; required

EXAMPLES
    pdlc prompt task-reviewer 236 --commits HEAD~2..HEAD
    pdlc prompt task-reviewer 236 --commits abc1234
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "task-reviewer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the reviewer's brief for one dispatch's commits")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--commits", required=True, help="revision or range the brief reads")
    args = parser.parse_args(command_args)

    return prompt.run(COMMAND, args, lambda: prompt.reviewer_brief(args.work_item, args.commits))


if __name__ == "__main__":
    raise SystemExit(main())
