#!/usr/bin/env python3
"""NAME
    pdlc inspect timeline - read-only: render evidence comments as a chronological timeline

USAGE
    pdlc inspect timeline WORK_ITEM           # compact index + cache file
    pdlc inspect timeline WORK_ITEM --full    # whole timeline to stdout

FLAGS
    --full    print the whole timeline to stdout instead of a compact index + cache file

DESCRIPTION
    Renders every PDLC evidence comment on a Work Item's parent
    work item as a chronological, stage-by-stage timeline — what each stage
    published, when, and by whom — so an agent can orient on the Work Item's
    history without reading every comment itself.

    By default the full timeline is written to the work-item cache and stdout
    carries only a compact index: one block per comment
    with its marker, local time, author, a one-line preview, and the line span
    to read from that file for the whole comment. A long history stays out of
    the context window while remaining one Read away.

    # Timeline — 2 evidence comment(s); full bodies in <cache-root>/.pdlc/cache/18/pdlc-timeline-18-<random>.md

    ## PRODUCT — 2026-08-01 21:14 UTC (@sudara)
       Scope: full product specification, 14 requirements over 4 constraints.
       Read lines 3-48 in <cache-root>/.pdlc/cache/18/pdlc-timeline-18-<random>.md for the full comment.

    ## APPROVED — 2026-08-02 22:00 UTC (@sudara)
       Product approved; advancing to UI.
       Read lines 50-54 in <cache-root>/.pdlc/cache/18/pdlc-timeline-18-<random>.md for the full comment.

    2 comment(s) without a PDLC marker were skipped.

`--full` prints the same content the cache file holds:

    # Timeline

    ## PRODUCT — 2026-08-01 21:14 UTC (@sudara)
    https://github.com/acme/example/issues/18#issuecomment-1

    <comment body, with its PDLC-<MARKER> stamp stripped>

With no evidence comments at all, both modes print:

    No PDLC evidence comments found
"""

from __future__ import annotations

import sys


from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.scratch import scratch_path, write_scratch
from pdlc.internal.workitem import comments_for_issue, resolve_item, timeline_compact, timeline_markdown
from pdlc.internal.failure import report_failure

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

        path = write_scratch(scratch_path(issue, f"timeline-{issue}"), full_text)
        sys.stdout.write(timeline_compact(issue, str(path), comments=comments))
    except PdlcError as error:
        return report_failure(error)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
