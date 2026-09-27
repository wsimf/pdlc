#!/usr/bin/env python3
"""NAME
    pdlc prompt acceptance-test-writer - read-only: write the test writer's brief for a record's whole implemented scope

USAGE
    pdlc prompt acceptance-test-writer WORK_ITEM --traceability FILE|text:BODY
        [--findings FILE|text:BODY]

DESCRIPTION
    Writes the complete brief for the test writer covering every implemented
    task of a record with requirement-to-source acceptance tests. It prints only
    the brief file's path; that file is sent to that sub-agent verbatim.

    It refuses, printing the reason and writing nothing, whenever `pdlc inspect
    test` reads not ready, and when no task has closed with its implementation
    recorded. The in-scope source is the union of the files every in-scope
    task's registered pull requests touched, in the order `pdlc inspect test`
    lists them, so the brief covers exactly the scope that command reports.

    It takes the traceability map, which no record carries: the caller builds
    it and passes the same file to `pdlc post test --traceability` unchanged.

    The brief's `## Findings to address` carries, verbatim, every change
    request the stage has received since it last published, read off the
    record — review findings, a Verification bounce, a CI failure note, a
    decision resolution, or an invalidation. `--findings` appends what the
    record cannot carry, such as a red check's name and log excerpt. With
    neither, the section is omitted.

    The brief also carries every patch or invalidation of an upstream stage
    since this stage last published, under `Changed since last publish`; with
    none, or before its first publication, that section is omitted.

FLAGS
    --traceability FILE|text:BODY  the traceability map the coverage is written
                            against; required
    --findings FILE|text:BODY  findings the record does not carry, appended
                            after the record's own open change requests

EXAMPLES
    pdlc prompt acceptance-test-writer 236 --traceability /tmp/trace.md
    pdlc prompt acceptance-test-writer 236 --traceability /tmp/trace.md \\
        --findings /tmp/red-checks.md
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "acceptance-test-writer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the test writer's brief for a record's whole implemented scope")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--traceability", required=True, help="the traceability map (FILE or text:BODY)")
    parser.add_argument("--findings", help="findings the record does not carry (FILE or text:BODY)")
    args = parser.parse_args(command_args)

    return prompt.run(
        COMMAND,
        args,
        lambda: prompt.acceptance_test_writer_brief(args.work_item, args.traceability, args.findings),
    )


if __name__ == "__main__":
    raise SystemExit(main())
