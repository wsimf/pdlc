#!/usr/bin/env python3
"""NAME
    pdlc inspect changes - read-only: the change requests a stage has not yet addressed

USAGE
    pdlc inspect changes WORK_ITEM [--stage STAGE]

FLAGS
    --stage STAGE    the stage to report on instead of the work item's current Status

DESCRIPTION
    Lists every change request a work item's stage has received since that
    stage last published its work, oldest first, with each request's full text.

A change request is any recorded ask for rework aimed at the stage: review
findings (Changes Required), a reviewer's blocking decision (Decision
Required), a Verification bounce back to the stage, a CI failure note, a
decision resolution, or a driver invalidation. A stage's publication (its own
evidence comment; for Verification, its review) is its claim to have addressed
everything asked before it, so only requests posted after the latest one are
listed. A stage that has never published lists every request aimed at it.
Decision questions are not listed separately: their text is already part of
the review that raised them.

Each request shows its source, local time, author, link, and body with the
`PDLC-*` stamp and review metadata stripped:

    # Open Changes — Implementation

    Implementation last published at 2026-08-01 21:14 UTC.

    ## 1. Review findings — 2026-08-02 09:30 UTC (@reviewer)
    https://github.com/acme/example/issues/18#issuecomment-7

    ## Findings

    - TASK-003 drops the retry on a 503.

    ## 2. CI failure — 2026-08-03 11:02 UTC (@pdlc)
    https://github.com/acme/example/issues/18#issuecomment-9

    CI failed stage: Implementation
    ...

With nothing open it prints `No open change requests for <stage>.` after the
publication line. The command writes nothing.

EXAMPLES
    pdlc inspect changes 18
    pdlc inspect changes 18 --stage "Technical Plan"
"""

from __future__ import annotations

import argparse
import sys

from pdlc.domain.changes import SOURCE_LABELS, OpenChanges, open_change_requests
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import evidence_comment_text, item_status, timeline_formatted_at
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.workitem import comments_for_issue, pipeline_for_item, resolve_item
from pdlc.internal.failure import report_failure

def render(changes: OpenChanges) -> str:
    lines = [f"# Open Changes — {changes.stage}", ""]
    if changes.published is None:
        lines.append(f"{changes.stage} has not published yet.")
    else:
        lines.append(f"{changes.stage} last published at {timeline_formatted_at(changes.published['createdAt'])}.")
    if not changes.requests:
        lines += ["", f"No open change requests for {changes.stage}."]
    for number, request in enumerate(changes.requests, start=1):
        comment = request.comment
        author = (comment.get("author") or {}).get("login", "unknown")
        lines += [
            "",
            f"## {number}. {SOURCE_LABELS[request.source]} — {timeline_formatted_at(comment['createdAt'])} (@{author})",
        ]
        if comment.get("url"):
            lines.append(comment["url"])
        lines += ["", evidence_comment_text(comment)]
    return "\n".join(lines) + "\n"


def inspect_changes(issue: str, stage: str | None) -> str:
    item = resolve_item(issue)
    pipeline = pipeline_for_item(item)
    target = stage or item_status(item)
    if target not in pipeline.active_stage_names:
        valid = ", ".join(pipeline.active_stage_names)
        raise PdlcError(f"no open changes to report for stage {target!r}; pass --stage with one of: {valid}")
    return render(open_change_requests(comments_for_issue(issue), pipeline, target))


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="List a stage's open change requests")
    parser.add_argument("work_item")
    parser.add_argument("--stage", help="Stage to report on instead of the current Status")
    args = parser.parse_args(command_args)

    try:
        sys.stdout.write(inspect_changes(args.work_item, args.stage))
    except PdlcError as error:
        return report_failure(error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
