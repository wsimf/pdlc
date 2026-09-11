#!/usr/bin/env python3
"""NAME
    pdlc inspect timeline - read-only: render evidence comments as a chronological timeline

USAGE
    pdlc inspect timeline WORK_ITEM           # compact index + temp file
    pdlc inspect timeline WORK_ITEM --full    # whole timeline to stdout

FLAGS
    --full    print the whole timeline to stdout instead of a compact index + temp file

DESCRIPTION
    Renders every PDLC evidence comment on a Work Item's parent
    work item as a chronological, stage-by-stage timeline — what each stage
    published, when, and by whom — so an agent can orient on the Work Item's
    history without reading every comment itself.

    By default the full timeline is written to a file under the system temp
    directory and stdout carries only a compact index: one block per comment
    with its marker, local time, author, a one-line preview, and the line span
    to read from that file for the whole comment. A long history stays out of
    the context window while remaining one Read away.

    # Timeline — 2 evidence comment(s); full bodies in /tmp/pdlc-timeline-18.md

    ## PRODUCT — 2026-08-01 21:14 UTC (@sudara)
       Scope: full product specification, 14 requirements over 4 constraints.
       Read lines 3-48 in /tmp/pdlc-timeline-18.md for the full comment.

    ## APPROVED — 2026-08-02 22:00 UTC (@sudara)
       Product approved; advancing to UI.
       Read lines 50-54 in /tmp/pdlc-timeline-18.md for the full comment.

    2 comment(s) without a PDLC marker were skipped.

`--full` prints the same content the temp file holds:

    # Timeline

    ## PRODUCT — 2026-08-01 21:14 UTC (@sudara)
    https://github.com/acme/example/issues/18#issuecomment-1

    <comment body, with its PDLC-<MARKER> stamp stripped>

With no evidence comments at all, both modes print:

    No PDLC evidence comments found
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.workitem import comments_for_issue, ref_label, resolve_item, timeline_compact, timeline_markdown

NO_EVIDENCE = "No PDLC evidence comments found\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    args = [arg for arg in command_args if arg not in ("--full",)]
    full = "--full" in command_args

    if wants_help(command_args):
        print_help(__doc__)
        return 0
    if len(args) != 1:
        print("usage: pdlc inspect timeline WORK_ITEM [--full]", file=sys.stderr)
        return 1
    issue = args[0]

    try:
        resolve_item(issue)
        comments = comments_for_issue(issue)
        if full:
            sys.stdout.write(timeline_markdown(issue, comments=comments).rstrip("\n") + "\n")
            return 0

        timeline_text = timeline_markdown(issue, comments=comments)
        full_text = timeline_text.rstrip("\n") + "\n"
        if timeline_text == NO_EVIDENCE:
            sys.stdout.write(full_text)
            return 0

        path = Path(tempfile.gettempdir()) / f"{ref_label()}-timeline-{issue}.md"
        path.write_text(full_text, encoding="utf-8")
        sys.stdout.write(timeline_compact(issue, str(path), comments=comments))
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
