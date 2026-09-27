#!/usr/bin/env python3
"""NAME
    pdlc prompt cumulative-reviewer - read-only: write the brief for the cumulative-review sub-agent

USAGE
    pdlc prompt cumulative-reviewer --shipped FILE|text:BODY --unchanged FILE|text:BODY --constraints FILE|text:BODY [--scope FILE|text:BODY]

DESCRIPTION
    Writes the complete brief for the general-purpose sub-agent that runs the
    project's configured cumulative-review capability over a record's whole
    change scope. It prints only the brief file's path; that file is sent to
    that sub-agent verbatim.

    Unlike every other `prompt` brief, this one takes no work item: the
    sub-agent knows nothing about PDLC, so nothing in the brief is resolved
    from a record. `--shipped`, `--unchanged`, and `--constraints` carry the
    record's intent already translated to plain language — the sub-agent
    cannot resolve an `FR-*`/`C-*` identifier, so that translation is the
    caller's own judgment, not a mechanical fact this command can derive.

    `--scope` defaults to "The current branch's diff against its base
    branch", the common case for work still unmerged on its own branch; pass
    it explicitly when the record's work already landed in pieces and no
    meaningful branch diff remains, or when only specific files cover the
    actual change scope.

FLAGS
    --shipped FILE|text:BODY      behaviour intended to change; required
    --unchanged FILE|text:BODY    adjacent behaviour that must not change; required
    --constraints FILE|text:BODY  the record's binding constraints, in plain terms; required
    --scope FILE|text:BODY        the change scope to review; defaults to the branch diff

EXAMPLES
    pdlc prompt cumulative-reviewer \\
      --shipped text:"routes retry a dropped connection with backoff" \\
      --unchanged text:"existing sync behaviour when online" \\
      --constraints text:"must not retry more than 3 times; no UI change"
    pdlc prompt cumulative-reviewer --shipped s.md --unchanged u.md --constraints c.md --scope text:"The commit range abc123..def456"
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "cumulative-reviewer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the brief for the cumulative-review sub-agent")
    parser.add_argument("--shipped", required=True, help="behaviour intended to change")
    parser.add_argument("--unchanged", required=True, help="adjacent behaviour that must not change")
    parser.add_argument("--constraints", required=True, help="the record's binding constraints, in plain terms")
    parser.add_argument("--scope", help="the change scope to review; defaults to the branch diff")
    prompt.add_inline_argument(parser)
    args = parser.parse_args(command_args)
    args.work_item = "review"  # no record backs this brief; only the scratch filename needs a name

    return prompt.run(
        COMMAND, args,
        lambda: prompt.cumulative_reviewer_brief(args.shipped, args.unchanged, args.constraints, args.scope),
    )


if __name__ == "__main__":
    raise SystemExit(main())
