"""A record's pull requests, resolved from the explicit registry.

A record's pull requests are exactly the ones registered on it and on its
delivery tasks — by `pdlc post implement-task`, `pdlc post attach-pr`, or the
implementation/testing transitions. They are never inferred from a PR body
keyword (`Closes #N`) or a branch name. This facade turns that registered
`PullRef` list into full PR dicts via the code host, and owns how a ref is
shown: a PR in the configured code repository reads as `#N` (and as a bare
number in JSON output), one from another repository as `owner/name#N`.
"""

from __future__ import annotations

from typing import Any

from pdlc.config import get_config
from pdlc.domain.records import PullRef, PullRequest, pull_ref, validate_pull_request
from pdlc.hosts.workitem_host import get_backend
from pdlc.hosts.code_host import get_code_host
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.workitem import resolve_item
from pdlc.internal.trace import console_debug


def pr_label(pr: PullRef | PullRequest | dict[str, Any]) -> str:
    """`#N` for a PR in the configured code repository, else `owner/name#N`."""
    ref = pr if isinstance(pr, PullRef) else PullRef(pr["number"], pr["repository"])
    return ref.label(get_config().pull_request_repository())


def prs_json(refs: list[PullRef]) -> list[int | str]:
    """`refs` for command output: numbers for the configured code
    repository's PRs, `owner/name#N` for any other repository's."""
    default = get_config().pull_request_repository()
    return [ref.json(default) for ref in refs]


def pr_output(pr: dict[str, Any]) -> dict[str, Any]:
    """A PR dict for command output: `number` in `prs_json` form, without the
    `repository` and `label` it folds in, so a single-repository record reads
    exactly as it did before PRs were repository-qualified."""
    shown = {key: value for key, value in pr.items() if key not in ("repository", "label")}
    return {**shown, "number": PullRef(pr["number"], pr["repository"]).json(get_config().pull_request_repository())}


def registered_prs(ref: str, *, record: dict | None = None, tasks: list[dict] | None = None) -> list[PullRef]:
    """Every pull request registered on the record `ref` or one of its
    delivery tasks, ascending and de-duplicated."""
    record = record or resolve_item(ref)
    refs: set[PullRef] = set(record.get("prs") or [])
    if tasks is None:
        refs.update(get_backend().task_prs(ref))
    else:
        for task in tasks:
            refs.update(task.get("prs") or [])
    return sorted(refs)


def record_pull_requests(ref: str, *, record: dict | None = None, tasks: list[dict] | None = None) -> list[dict]:
    """The registered pull requests for `ref` as full dicts (see
    `code_host.pull_requests`). Empty when none are registered."""
    refs = registered_prs(ref, record=record, tasks=tasks)
    console_debug(f"loading {len(refs)} registered PR(s) for work item {ref!r}")
    resolved = get_code_host().pull_requests(refs) if refs else []
    if {pull_ref(pr) for pr in resolved} != set(refs):
        raise PdlcError("code host returned fewer pull requests than the registry; refusing to continue")
    return [validate_pull_request({**pr, "label": pr_label(pr)}) for pr in resolved]


def record_open_review_comments(ref: str, *, record: dict | None = None, tasks: list[dict] | None = None) -> list[dict]:
    """Every still-unresolved review-thread comment across the record's
    registered pull requests (see `code_host.unresolved_review_comments`),
    each stamped with its `pr` ref, ascending by PR then host order.
    Empty when no PR is registered or every thread is resolved."""
    refs = registered_prs(ref, record=record, tasks=tasks)
    console_debug(f"loading review threads from {len(refs)} PR(s) for work item {ref!r}")
    host = get_code_host()
    comments = []
    for pr in refs:
        for comment in host.unresolved_review_comments(pr):
            comments.append({"pr": pr, **comment})
    return comments


# One rendering of live review-thread state, shared by every command that
# surfaces it, so a skill reads the same `## Open Comments` section wherever it
# appears. Nothing here resolves a thread or decides it is in scope; that
# judgment stays with the caller. `lead` is the one line a command adds to
# route its own caller when threads are open.
def open_review_comments_section(
    comments: list[dict], *, lead: str | None = None, none_text: str = "None."
) -> list[str]:
    """The `## Open Comments` section for `comments`, as output lines."""
    if not comments:
        return ["## Open Comments", "", none_text]

    sections = ["## Open Comments", ""]
    if lead is not None:
        sections += [lead, ""]
    by_pr: dict[PullRef, list[dict]] = {}
    for comment in comments:
        by_pr.setdefault(comment["pr"], []).append(comment)

    for pr in sorted(by_pr):
        sections.append(f"PR {pr_label(pr)}:")
        for comment in by_pr[pr]:
            where = f" on {comment['path']}:{comment['line']}" if comment.get("path") else ""
            sections.append(f"- @{comment['author']}{where} — {comment['body']} ({comment['url']})")
        sections.append("")
    return sections[:-1] if sections[-1] == "" else sections
