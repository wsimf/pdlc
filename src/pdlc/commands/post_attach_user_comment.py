"""NAME
    pdlc post attach-user-comment - add a discussion comment to a work item

USAGE
    pdlc post attach-user-comment WI --body FILE|-|text:BODY

DESCRIPTION
    Posts a discussion comment on a work item or delivery task under the authenticated account.

The body is preserved without a PDLC marker and appears under User Comments in `pdlc inspect` or `pdlc inspect task`.
This command changes no lifecycle state, gate, or evidence.
Blank bodies, bodies starting with `PDLC-`, and bodies whose first non-empty line is `## Technical Plan` or `## Implementation` are refused because they can be interpreted as workflow evidence.
Repeated successful calls create separate comments.

Returns JSON containing the work item number and the posted comment reference:
    {"workItem": 47, "comment": "https://github.com/owner/repo/issues/47#issuecomment-123"}

Transient failures before sending are retried automatically and exit 75 if they persist.
A transient failure after sending may have posted the comment; exit 76 prints a read-only comment check before any retry.
Other failures exit 1 with `pdlc: <error>`.

FLAGS
    --body FILE|-|text:BODY    required; read a UTF-8 file, stdin, or inline text

EXAMPLES
    pdlc post attach-user-comment 47 --body text:"Keep this behind a flag."
    pdlc post attach-user-comment 47 --body comment.md
"""

from __future__ import annotations

import argparse
import json
import sys

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import TASK_EVIDENCE_HEADINGS
from pdlc.internal.failure import Recovery, report_failure, set_recovery
from pdlc.internal.inputs import assert_unmarked, print_help, resolve_text, wants_help
from pdlc.internal.workitem import post_comment


def post_attach_user_comment(work_item: str, body_source: str) -> dict[str, int | str]:
    if not work_item.isdigit():
        raise PdlcError(f"work item number must be numeric: {work_item}")
    body = resolve_text(body_source, label="comment body")
    assert_unmarked(body, "comment body")
    if body.lstrip().splitlines()[0].strip() in TASK_EVIDENCE_HEADINGS:
        raise PdlcError("comment body starts with a task evidence heading; write a discussion comment instead")

    set_recovery(Recovery(
        check=f"pdlc inspect comments {work_item} --page 1",
        landed="the comments show the submitted body under your account at the time of this attempt",
        otherwise="follow any next-page commands until all comments from this attempt's time are checked; re-run only if the comment is absent: {rerun}",
        note="A re-run after the comment landed creates a duplicate. Keep the input file until success; if the result is ambiguous, stop and report it.",
    ))
    return {"workItem": int(work_item), "comment": post_comment(work_item, body)}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(args):
        print_help(__doc__)
        return 0
    parser = argparse.ArgumentParser(description="Add a discussion comment to a work item")
    parser.add_argument("work_item")
    parser.add_argument("--body", required=True)
    parsed = parser.parse_args(args)
    try:
        result = post_attach_user_comment(parsed.work_item, parsed.body)
    except PdlcError as error:
        return report_failure(error)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
