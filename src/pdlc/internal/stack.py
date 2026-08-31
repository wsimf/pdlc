"""Branch naming and stack entry points for GitHub delivery-task pull requests.

Each delivery task owns one branch whose pull request stacks onto the previous
implemented task's. The `gh stack` extension owns the stack itself — its order,
its bases, its rebases, and which branches have landed. Nothing here re-derives
any of that; these helpers only translate PDLC identities (task ids, registered
pull requests) into the arguments `gh stack` expects.
"""

from __future__ import annotations


def task_branch_name(slug: str, task_id: str) -> str:
    """Deterministic branch for one delivery task, e.g. ``pdlc/record-142/task-003``.

    Branch naming is the one piece of stack vocabulary PDLC owns: it ties a
    branch back to the task identity. Everything else about the stack is read
    back from `gh stack`.
    """
    return f"pdlc/{slug}/{task_id.lower()}"


def stack_entry_pr(delivery_tasks: list[dict], chosen: dict) -> int | None:
    """The pull request to hand `gh stack checkout` so the local stack for
    ``chosen`` is set up before its branch is added, or None when ``chosen`` is
    the first task and the stack must be created with `gh stack init`.

    This is the highest-numbered already-implemented task before ``chosen``, read
    from the explicit PR registry — never from a branch name or a remote branch
    listing. `gh stack checkout <pr>` discovers the rest of the stack from GitHub
    itself, so one registered number is enough even on a fresh clone.
    """
    prior = [
        task
        for task in delivery_tasks
        if task.get("taskId")
        and task["number"] < chosen["number"]
        and task.get("hasImplementation")
        and task.get("prs")
    ]
    if not prior:
        return None
    latest = max(prior, key=lambda task: task["number"])
    return max(latest["prs"])
