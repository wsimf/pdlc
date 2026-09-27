#!/usr/bin/env python3
"""NAME
    pdlc prompt task-test-writer - read-only: write the test writer's brief for one dispatch's change

USAGE
    pdlc prompt task-test-writer WORK_ITEM --commits REVISIONS
        --report FILE|text:BODY --traceability FILE|text:BODY
        [--findings FILE|text:BODY]

DESCRIPTION
    Writes the complete brief for the test writer covering what one dispatch
    changed in the unit a record has next, scoped to that task's unit coverage.
    It prints only the brief file's path; that file is sent to that sub-agent
    verbatim.

    The test writer reads a change that exists only in the working tree, so it
    takes the revisions to read. They are the caller's to pass because the range
    is one dispatch's, not the branch's: a second pass, or a fix landing on top of
    implemented code, leaves the earlier commits on that same branch, so a range
    worked out from the branch would cover work that was already covered.

    It also takes the two artifacts no record carries — what the implementing
    agent reported it did, and the traceability map the coverage is written
    against. The report is handed over before it is recorded: the implementing
    agent reports back, the coverage is written against what it says, and the
    summary reaches the task's `## Implementation` comment only once the task
    lands.

    The test writer is the project's configured test-writer agent, and the brief
    holds it to the same task, plan, and acceptance criteria the implementer was
    given on this pass.

FLAGS
    --commits REVISIONS     the revision or range the brief reads, as `git show`
                            accepts it; required
    --report FILE|text:BODY the implementing agent's report-back, carried into
                            the brief's `## What changed`; required
    --traceability FILE|text:BODY  the traceability map the coverage is written
                            against; required
    --findings FILE|text:BODY  reviewer findings accepted as non-blocking;
                            "none" when omitted

EXAMPLES
    pdlc prompt task-test-writer 236 --commits HEAD~2..HEAD \\
        --report /tmp/impl-report.md --traceability /tmp/trace.md
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "task-test-writer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the test writer's brief for one dispatch's change")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--commits", required=True, help="revision or range the brief reads")
    parser.add_argument("--report", required=True, help="the implementing agent's report-back (FILE or text:BODY)")
    parser.add_argument("--traceability", required=True, help="the traceability map (FILE or text:BODY)")
    parser.add_argument("--findings", help="accepted non-blocking review findings (FILE or text:BODY)")
    args = parser.parse_args(command_args)

    return prompt.run(
        COMMAND,
        args,
        lambda: prompt.test_writer_brief(
            args.work_item, args.commits, args.report, args.traceability, args.findings,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
