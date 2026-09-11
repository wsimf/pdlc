"""A record's pull requests, resolved from the explicit registry.

A record's pull requests are exactly the ones registered on it and on its
delivery tasks — by `pdlc post implement-task`, `pdlc post attach-pr`, or the
implementation/testing transitions. They are never inferred from a PR body
keyword (`Closes #N`) or a branch name. This facade turns that registered
number list into full PR dicts via the code host.
"""

from __future__ import annotations

from pdlc.domain.records import validate_pull_request
from pdlc.hosts.workitem_host import get_backend
from pdlc.hosts.code_host import get_code_host
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.workitem import resolve_item


def registered_pr_numbers(ref: str, *, record: dict | None = None, tasks: list[dict] | None = None) -> list[int]:
    """Every pull-request number registered on the record `ref` or one of its
    delivery tasks, ascending and de-duplicated."""
    record = record or resolve_item(ref)
    numbers: set[int] = set(record.get("prs") or [])
    if tasks is None:
        numbers.update(get_backend().task_pr_numbers(ref))
    else:
        for task in tasks:
            numbers.update(task.get("prs") or [])
    return sorted(numbers)


def record_pull_requests(ref: str, *, record: dict | None = None, tasks: list[dict] | None = None) -> list[dict]:
    """The registered pull requests for `ref` as full dicts (see
    `code_host.pull_requests_by_number`). Empty when none are registered."""
    numbers = registered_pr_numbers(ref, record=record, tasks=tasks)
    resolved = get_code_host().pull_requests_by_number(numbers) if numbers else []
    if {pr.get("number") for pr in resolved} != set(numbers):
        raise PdlcError("code host returned fewer pull requests than the registry; refusing to continue")
    return [validate_pull_request(pr) for pr in resolved]


def record_open_review_comments(ref: str, *, record: dict | None = None, tasks: list[dict] | None = None) -> list[dict]:
    """Every still-unresolved review-thread comment across the record's
    registered pull requests (see `code_host.unresolved_review_comments`),
    each stamped with its `pr` number, ascending by PR then host order.
    Empty when no PR is registered or every thread is resolved."""
    numbers = registered_pr_numbers(ref, record=record, tasks=tasks)
    host = get_code_host()
    comments = []
    for number in numbers:
        for comment in host.unresolved_review_comments(number):
            comments.append({"pr": number, **comment})
    return comments
