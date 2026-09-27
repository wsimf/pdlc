#!/usr/bin/env python3
"""NAME
    pdlc prompt tasks-reviewer - write the reviewer's brief for a UI fragment or Tasks breakdown; nothing is published to the backend

USAGE
    - if reviewing a local, unpublished breakdown or UI fragment:
        pdlc prompt tasks-reviewer WORK_ITEM (--manifest FILE | --fragment FILE) [--findings FILE|text:BODY]
    - if reviewing the published UI section or breakdown as it stands:
        pdlc prompt tasks-reviewer WORK_ITEM [--findings FILE|text:BODY]

DESCRIPTION
    Writes the complete brief for the reviewer checking a UI fragment or Tasks
    breakdown before it is posted to the work item store. It prints only the
    brief file's path; that file is sent to that sub-agent verbatim.

    At most one of `--manifest` or `--fragment` is given: `--manifest`
    names the Tasks-stage manifest `pdlc post tasks --stage Tasks` takes; the
    brief lists each entry's body file path rather than inlining it, except a
    removed task's stored body, which has no file of its own and is inlined.
    `--fragment` names the file holding the UI section's content for the UI
    stage, the same file `pdlc post tasks --stage UI --body` lands; the brief
    names its path rather than inlining it. The parent's
    complete body is always inlined, so the reviewer can check every cited
    `FR-*`/`C-*`/`UJ-*` without a second read; for a fragment review, the
    parent's own `## UI` section is left out, since the fragment replaces it.

    With neither, the command writes the artifact the record's status names —
    the published `## UI` section, or a manifest retaining every published
    task — to fresh files in the work-item cache and names them in the brief,
    so a published artifact can be reviewed and landed unchanged. It refuses
    when the record is at neither stage or has nothing published.

    The command records the exact files it hands the reviewer in the work-item
    cache — the fragment, or the manifest and its task body files — and
    `pdlc post tasks` lands only those files unchanged. If a file
    recorded by an earlier review changed since, the command first restores
    each to the reviewed version, keeps the edited copy beside it as
    `<name>.rejected.<ext>`, and refuses so that review is discarded and redone.

    `--findings` carries the previous pass's findings on a re-review, so each
    can be confirmed addressed; with nothing given, the brief has no prior
    findings section.

    The command also writes a fresh findings file, an outline of the report,
    to a fixed path in the work-item cache and names it in the brief; the
    reviewer writes its findings there. Each brief overwrites the previous
    one's file, after reading `--findings`, so that file may be passed back as
    `--findings` on the re-review. A successful landing of the reviewed
    files deletes it.

FLAGS
    --manifest FILE              a Tasks-stage manifest; mutually exclusive with --fragment
    --fragment FILE              the proposed UI section's file; mutually exclusive with --manifest
    --findings FILE|text:BODY    the previous pass's findings, on a re-review

EXAMPLES
    pdlc prompt tasks-reviewer 236 --manifest /tmp/pdlc-tasks.json
    pdlc prompt tasks-reviewer 236 --fragment /tmp/pdlc-ui.md
    pdlc prompt tasks-reviewer 236
    pdlc prompt tasks-reviewer 236 --manifest /tmp/pdlc-tasks.json --findings text:"tighten TASK-2"
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "tasks-reviewer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the reviewer's brief for a UI fragment or Tasks breakdown")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--manifest", help="a Tasks-stage manifest file")
    parser.add_argument("--fragment", help="a UI section's content FILE")
    parser.add_argument("--findings", help="the previous pass's findings (FILE or text:BODY)")
    args = parser.parse_args(command_args)

    return prompt.run(
        COMMAND, args,
        lambda: prompt.tasks_reviewer_brief(args.work_item, args.manifest, args.fragment, args.findings),
    )


if __name__ == "__main__":
    raise SystemExit(main())
