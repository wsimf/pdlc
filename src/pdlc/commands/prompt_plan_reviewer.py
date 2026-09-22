#!/usr/bin/env python3
"""NAME
    pdlc prompt plan-reviewer - read-only: print the reviewer's brief for a pass's delivery-task plans

USAGE
    pdlc prompt plan-reviewer WORK_ITEM --manifest FILE [--findings FILE|text:BODY] [--file]

DESCRIPTION
    Prints the complete brief for the reviewer checking a pass's delivery-task
    plans before they are posted to the work item store. The output is sent
    to that sub-agent verbatim.

    `--manifest` is the same `[{"id": "TASK-N", "plan": FILE}, ...]` array
    `pdlc post plan` takes. For each entry, the brief inlines the named
    task's current body and any existing `## Technical Plan` comment straight
    off the record, then the proposed plan file's full contents — the
    manifest need only point at the plan file. The parent's complete body is
    always inlined too.

    `--findings` carries the previous pass's findings on a re-review, so each
    can be confirmed addressed; with nothing given, that section renders
    "none, first review".

FLAGS
    --manifest FILE             the plans manifest; required
    --findings FILE|text:BODY   the previous pass's findings, on a re-review
    --file                      write the brief to
                                {TEMPDIR}/{repo}-prompt-plan-reviewer-{work item}.md
                                and print that path, instead of stdout

EXAMPLES
    pdlc prompt plan-reviewer 236 --manifest /tmp/pdlc-plan.json
    pdlc prompt plan-reviewer 236 --manifest /tmp/pdlc-plan.json --findings text:"resolve the spike"
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "plan-reviewer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the reviewer's brief for a pass's delivery-task plans")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--manifest", required=True, help="the plans manifest file")
    parser.add_argument("--findings", help="the previous pass's findings (FILE or text:BODY)")
    args = parser.parse_args(command_args)

    return prompt.run(COMMAND, args, lambda: prompt.plan_reviewer_brief(args.work_item, args.manifest, args.findings))


if __name__ == "__main__":
    raise SystemExit(main())
