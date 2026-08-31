"""A record's pull requests, resolved from the explicit registry.

A record's pull requests are exactly the ones registered on it and on its
delivery tasks — by `pdlc post implement-task`, `pdlc post attach-pr`, or the
implementation/testing transitions. They are never inferred from a PR body
keyword (`Closes #N`) or a branch name. This facade turns that registered
number list into full PR dicts via the code host.
"""

from __future__ import annotations

from pdlc.hosts.code_host import get_code_host
from pdlc.internal.workitem import read_task_meta, resolve_item, task_tree


def registered_pr_numbers(ref: str) -> list[int]:
    """Every pull-request number registered on the record `ref` or one of its
    delivery tasks, ascending and de-duplicated."""
    numbers: set[int] = set()
    record = resolve_item(ref)
    for value in read_task_meta(record.get("issueBody") or "").get("prs", []):
        if value.isdigit():
            numbers.add(int(value))
    for task in task_tree(ref):
        numbers.update(task.get("prs") or [])
    return sorted(numbers)


def record_pull_requests(ref: str) -> list[dict]:
    """The registered pull requests for `ref` as full dicts (see
    `code_host.pull_requests_by_number`). Empty when none are registered."""
    numbers = registered_pr_numbers(ref)
    return get_code_host().pull_requests_by_number(numbers) if numbers else []
