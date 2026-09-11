#!/usr/bin/env python3
"""NAME
    pdlc inspect task timeline - read-only: render one delivery task's evidence as a chronological timeline

USAGE
    pdlc inspect task timeline DELIVERY_TASK           # compact index + temp file
    pdlc inspect task timeline DELIVERY_TASK --full    # whole timeline to stdout

FLAGS
    --full    print the whole timeline to stdout instead of a compact index + temp file

DESCRIPTION
    Renders one delivery task's own comment stream as a chronological
    timeline — plan, implementation, and invalidation, in the order they
    happened — so an agent can tell what state a task is really in without
    cross-referencing `hasPlan`/`hasImplementation`/`needsPlan` against raw
    comments itself.

    Unlike `pdlc inspect timeline`, which only shows a parent record's
    `PDLC-*`-marked comments, a task's most important evidence — its
    `## Technical Plan` and `## Implementation` comments — carries no marker
    at all, so this renders two kinds of entry: real `PDLC-*` markers (e.g.
    `PDLC-INVALIDATED`, posted when the task is reopened) and synthetic
    `PLAN`/`IMPLEMENTATION` entries for the unmarked evidence comments.

    `pdlc post invalidate` deletes a reopened task's stale `## Technical
    Plan`/`## Implementation` comments outright rather than editing them in
    place, so they leave no `INVALIDATED` entry of their own — once a task is
    reopened, its earlier `PLAN`/`IMPLEMENTATION` entries are gone from this
    timeline too, and only the reopen's own `PDLC-INVALIDATED` entry (plus any
    evidence posted since) remains.

    By default the full timeline is written to a file under the system temp
    directory and stdout carries only a compact index: one block per entry
    with its marker, local time, author, a one-line preview, and the line
    span to read from that file for the whole entry.

    # Timeline — 3 evidence entry(s); full bodies in /tmp/pdlc-task-timeline-641.md

    ## PLAN — 2026-08-01 21:14 UTC (@sudara)
       Add the validation helper and wire it into the write path.
       Read lines 3-9 in /tmp/pdlc-task-timeline-641.md for the full entry.

    ## IMPLEMENTATION — 2026-08-03 10:02 UTC (@sudara)
       Shipped the endpoint.
       Read lines 11-16 in /tmp/pdlc-task-timeline-641.md for the full entry.

    ## INVALIDATED — 2026-08-04 09:00 UTC (@sudara)
       Invalidated stage: Technical Plan
       Read lines 18-24 in /tmp/pdlc-task-timeline-641.md for the full entry.

`--full` prints the same content the temp file holds, one `## MARKER — time
(@author)` section per entry with the task comment's URL and full body.

With no plan, implementation, or invalidation evidence at all, both modes
print:

    No task evidence comments found
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.workitem import comments_for_issue, ref_label, task_timeline_compact, task_timeline_markdown

NO_EVIDENCE = "No task evidence comments found\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    args = [arg for arg in command_args if arg not in ("--full",)]
    full = "--full" in command_args

    if wants_help(command_args):
        print_help(__doc__)
        return 0
    if len(args) != 1:
        print("usage: pdlc inspect task timeline DELIVERY_TASK [--full]", file=sys.stderr)
        return 1
    task = args[0]

    try:
        comments = comments_for_issue(task)
        if full:
            sys.stdout.write(task_timeline_markdown(task, comments=comments).rstrip("\n") + "\n")
            return 0

        timeline_text = task_timeline_markdown(task, comments=comments)
        full_text = timeline_text.rstrip("\n") + "\n"
        if timeline_text == NO_EVIDENCE:
            sys.stdout.write(full_text)
            return 0

        path = Path(tempfile.gettempdir()) / f"{ref_label()}-task-timeline-{task}.md"
        path.write_text(full_text, encoding="utf-8")
        sys.stdout.write(task_timeline_compact(task, str(path), comments=comments))
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
