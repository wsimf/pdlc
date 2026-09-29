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

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import TASK_TITLE_PATTERN
from pdlc.domain.workflow import Lifecycle
from pdlc.internal.workitem import (
    item_branch_slug,
    resolve_item,
    task_tree,
    tasks_by_number,
    workflow_for_item,
)
from pdlc.internal.vcs import contains_commit
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
    the work item's first task, which the code host puts on the current
    branch's stack or a new one.

    This is the highest-numbered already-implemented task before ``chosen``.
    `gh stack checkout <pr>` discovers the rest of the stack from GitHub itself,
    so one registered number is enough even on a fresh clone.
    """
    latest = latest_implemented_task(delivery_tasks, before=chosen["number"])
    return max(latest["prs"]) if latest else None


def stack_gaps(pull_requests: list[dict]) -> list[str]:
    """Open task PRs whose head commit HEAD does not include — a lower branch
    checked out, or a fix not yet restacked. Merged PRs are skipped: a squash
    merge rewrites their commits, so their code arrives through the base."""
    return [
        f"#{pr['number']} ({pr.get('branch') or 'unknown branch'}) @ {pr['headSha'][:12]}"
        for pr in pull_requests
        if pr.get("state") == "OPEN" and pr.get("headSha") and not contains_commit(pr["headSha"])
    ]


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
    return Predecessor(ref, False, task_branch_name(item_branch_slug(item), latest["taskId"]), max(latest["prs"]))


@dataclass(frozen=True)
class TaskCheckout:
    """One delivery task translated into the arguments a checkout needs.

    ``pr`` is the task's own registered pull request, ``entry_pr`` the previous
    implemented task's, and ``predecessor`` the `pdlc prepare --after` work item
    this task's worktree already sits on — in which case the branch is the
    current one and there is nothing to check out."""

    task: dict
    branch: str
    pr: int | None
    entry_pr: int | None
    predecessor: Predecessor | None


def parse_task_name(ref: str) -> tuple[str, str] | None:
    """``(parent work item, TASK-NNN)`` for a ``WORK-N-TASK-NNN`` name, else None."""
    match = TASK_TITLE_PATTERN.match(ref.strip().upper())
    return (match.group(1), match.group(2)) if match else None


def resolve_task_checkout(ref: str) -> TaskCheckout:
    """Resolve a delivery task by ``WORK-N-TASK-NNN`` name or by its own issue
    number, and return where its branch sits on the stack.

    A bare ``TASK-NNN`` is refused: it names no work item, and inferring one
    from the current checkout would make the same argument mean different tasks
    in different trees."""
    parsed = parse_task_name(ref)
    if parsed is None:
        if not ref.strip().isdigit():
            raise PdlcError(
                f"cannot resolve delivery task {ref!r}: pass its WORK-N-TASK-NNN name "
                "or its own issue number"
            )
        resolved = tasks_by_number([ref.strip()])
        if not resolved:
            raise PdlcError(f"no delivery task found for {ref!r}")
        parsed = parse_task_name(resolved[0].get("title") or "")
        if parsed is None:
            raise PdlcError(f"{ref} is not a delivery task: its title carries no WORK-N-TASK-NNN identity")

    parent, task_id = parsed
    item = resolve_item(parent)
    delivery = [task for task in task_tree(parent) if task.get("taskId")]
    chosen = next((task for task in delivery if task["taskId"] == task_id), None)
    if chosen is None:
        raise PdlcError(f"work item {parent} has no delivery task {task_id}")

    prs = chosen.get("prs") or []
    return TaskCheckout(
        task=chosen,
        branch=task_branch_name(item_branch_slug(item), task_id),
        pr=max(prs) if prs else None,
        entry_pr=stack_entry_pr(delivery, chosen),
        predecessor=after_predecessor(delivery, chosen),
    )


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
