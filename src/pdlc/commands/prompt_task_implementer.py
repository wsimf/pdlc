#!/usr/bin/env python3
"""NAME
    pdlc prompt task-implementer - read-only: write the implementer's brief for a work item's next unit

USAGE
    - if the unit is being dispatched for the first time on this pass:
        pdlc prompt task-implementer WORK_ITEM
    - if a task review returned findings for the unit:
        pdlc prompt task-implementer WORK_ITEM --findings FILE

DESCRIPTION
    Writes the complete brief for the sub-agent that writes the code of the unit
    a record has next, with every value already filled in. It prints only the
    brief file's path; that file is sent to that sub-agent verbatim.

    The sub-agent to send it to is the one `pdlc inspect task` names under
    `## Agent`. Everything else the brief interpolates is already on the
    record; the one artifact it takes is the task reviewer's findings file.

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

    The implementation brief also carries every patch or invalidation of an
    upstream stage since this stage last published, under `Changed since last
    publish`; with none, or before its first publication, that section is
    omitted.
    For a UI task it also lists every file attached to the work item under
    `Attachments`, each with its description and local path; a CORE task, or a
    work item with none, omits that section.

    With `--findings`, the brief for whichever form is due also carries the
    review's `### Implementation findings`, fixed with new commits on top:
    every `[blocking]` one, and each `[non-blocking]` one the agent judges
    worth applying, naming in its report which it applied. When that section
    holds no finding tagged `[blocking]`, no brief is written and the command
    exits 3 with:

        No implementation findings in FILE: the implementation agent is not
        needed and no brief was written. Continue with the skill's next step.

    A file missing its `### Implementation findings`, `### Test findings`, or
    `### Verdict` section, or whose verdict is not filled in, is refused.

FLAGS
    --findings FILE|text:BODY  the findings file the task-reviewer brief named,
                            as the reviewer filled it

EXAMPLES
    pdlc prompt task-implementer 236
    pdlc prompt task-implementer 236 --findings /tmp/task-review-findings.md
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
    parser.add_argument("--findings", help="the task reviewer's findings file (FILE or text:BODY)")
    args = parser.parse_args(command_args)

    return prompt.run(COMMAND, args, lambda: prompt.implementer_brief(args.work_item, args.findings))


if __name__ == "__main__":
    raise SystemExit(main())
