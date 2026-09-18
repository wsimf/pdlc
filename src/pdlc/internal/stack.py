"""Branch naming and stack entry points for GitHub delivery-task pull requests.

Each delivery task owns one branch whose pull request stacks onto the previous
implemented task's. The `gh stack` extension owns the stack itself — its order,
its bases, its rebases, and which branches have landed. Nothing here re-derives
any of that; these helpers only translate PDLC identities (task ids, registered
pull requests, a `pdlc prepare --after` predecessor) into the arguments
`gh stack` expects.
"""

from __future__ import annotations

from dataclasses import dataclass

from pdlc.domain.workflow import Lifecycle
from pdlc.internal.workitem import item_slug, resolve_item, task_tree, workflow_for_item
from pdlc.internal.worktree import worktree_after


def task_branch_name(slug: str, task_id: str) -> str:
    """Deterministic branch for one delivery task, e.g. ``pdlc/record-142/task-003``.

    Branch naming is the one piece of stack vocabulary PDLC owns: it ties a
    branch back to the task identity. Everything else about the stack is read
    back from `gh stack`.
    """
    return f"pdlc/{slug}/{task_id.lower()}"


def latest_implemented_task(delivery_tasks: list[dict], before: int | None = None) -> dict | None:
    """The highest-numbered delivery task with an implementation and a
    registered pull request, optionally only among tasks numbered below
    ``before``. Read from the explicit PR registry — never from a branch name or
    a remote branch listing."""
    candidates = [
        task
        for task in delivery_tasks
        if task.get("taskId")
        and (before is None or task["number"] < before)
        and task.get("hasImplementation")
        and task.get("prs")
    ]
    return max(candidates, key=lambda task: task["number"]) if candidates else None


def stack_entry_pr(delivery_tasks: list[dict], chosen: dict) -> int | None:
    """The pull request to hand `gh stack checkout` so the local stack for
    ``chosen`` is set up before its branch is added, or None when ``chosen`` is
    the first task and the stack must be created with `gh stack init`.

    This is the highest-numbered already-implemented task before ``chosen``.
    `gh stack checkout <pr>` discovers the rest of the stack from GitHub itself,
    so one registered number is enough even on a fresh clone.
    """
    latest = latest_implemented_task(delivery_tasks, before=chosen["number"])
    return max(latest["prs"]) if latest else None


@dataclass(frozen=True)
class Predecessor:
    """Where a work item prepared with `pdlc prepare --after` stacks on.

    ``complete`` means the predecessor has landed, so there is nothing left to
    stack on. Otherwise ``branch``/``pr`` name its latest implemented task, or
    are None when it has no implemented task with a registered PR yet."""

    ref: str
    complete: bool
    branch: str | None
    pr: int | None


def resolve_predecessor(ref: str) -> Predecessor:
    item = resolve_item(ref)
    pipeline, state = workflow_for_item(item)
    if state.stage == pipeline.terminal_stage and state.lifecycle == Lifecycle.COMPLETED:
        return Predecessor(ref, True, None, None)
    latest = latest_implemented_task(task_tree(ref))
    if latest is None:
        return Predecessor(ref, False, None, None)
    return Predecessor(ref, False, task_branch_name(item_slug(item), latest["taskId"]), max(latest["prs"]))


def after_predecessor(delivery_tasks: list[dict], chosen: dict) -> Predecessor | None:
    """The `pdlc prepare --after` predecessor ``chosen`` stacks onto, or None
    when ``chosen`` is not the first task of such a worktree (it already has an
    ordinary stack entry point — see `stack_entry_pr`) or the worktree was not
    prepared with `--after`.

    A predecessor whose branch may live in another, still-active worktree
    cannot be `gh stack checkout`-ed here, so callers route this case to
    `CodeHost.link_task_stack` instead of the ordinary checkout/add or
    sync/submit calls."""
    if stack_entry_pr(delivery_tasks, chosen) is not None:
        return None
    after = worktree_after()
    return resolve_predecessor(after) if after else None
