"""NAME
    pdlc inspect comments - read-only: show one bounded page of work-item comments

USAGE
    pdlc inspect comments ISSUE [--page N]

DESCRIPTION
    Pages contain 100 comments, newest first. The output includes the exact total
    and a ready-to-copy command whenever another page exists.
"""
from __future__ import annotations
import argparse
import sys
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.workitem import comments_page
from pdlc.internal.failure import report_failure

def inspect(issue: str, page: int) -> str:
    if not issue.isdigit():
        raise PdlcError(f"Issue number must be numeric: {issue}")
    result = comments_page(issue, page)
    lines = ["## Comments", "", f"Page {result.page} of {max(1, (result.total + 99) // 100)} ({result.total} total)", ""]
    for comment in result.comments:
        author = (comment.get("author") or {}).get("login") or "unknown"
        lines += [f"### {author} — {comment.get('createdAt') or 'unknown time'}", "", comment.get("body") or "", ""]
    if not result.comments:
        lines.append("No comments on this page.")
    if result.has_next:
        lines += ["", f"{result.total - result.page * 100} more comments; use pdlc inspect comments {issue} --page {page + 1}."]
    return "\n".join(lines).rstrip() + "\n"

def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    args = command_args
    if wants_help(args):
        print_help(__doc__)
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue")
    parser.add_argument("--page", type=int, default=1)
    parsed = parser.parse_args(args)
    try:
        sys.stdout.write(inspect(parsed.issue, parsed.page))
        return 0
    except PdlcError as error:
        return report_failure(error)
