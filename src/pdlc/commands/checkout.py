#!/usr/bin/env python3
"""NAME
    pdlc checkout - put the working tree on one delivery task's branch

USAGE
    pdlc checkout DELIVERY_TASK

DESCRIPTION
    Puts the working tree on the branch that belongs to one delivery task,
    creating it in the right place when it does not exist yet.

    DELIVERY_TASK is the task's `WORK-N-TASK-NNN` name or its own issue number.
    A bare `TASK-NNN` is refused: it names no work item, so the same argument
    would mean different tasks in different trees.

    Where the branch belongs is read from the record, never from the local
    checkout: the task's own registered pull request when it has been
    implemented, otherwise the previous implemented task's pull request as the
    stack entry, and a new stack when the task is the first. Which of those the
    code host turns into which commands is the host's own stack vocabulary; a
    host with no stacked-PR mechanism refuses rather than guessing a base
    branch. Nothing here rebases, pushes, or opens a pull request.

    The working tree must be clean; a dirty tree is reported and nothing is
    touched. For the first task of a worktree prepared with `pdlc prepare
    --after`, the worktree's current branch already is that branch, so the
    command reports that and changes nothing.

    On success it prints the task, the branch, and what the host did:

        WORK-142-TASK-004 [UI] Route profile chart
        branch: pdlc/record-142/task-004
        checked out pdlc/record-142/task-004 from its pull request #151

EXAMPLES
    pdlc checkout WORK-142-TASK-004
    pdlc checkout 51
"""

from __future__ import annotations

import sys

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.code_host import get_code_host
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.stack import TaskCheckout, resolve_task_checkout
from pdlc.internal.worktree import working_tree_dirty
from pdlc.internal.failure import Recovery, report_failure, set_recovery


def _action(target: TaskCheckout) -> str:
    # A `prepare --after` worktree's first task is already on its branch, and
    # that branch may be checked out in the predecessor's own still-active
    # worktree. Nothing to check out, so nothing is run.
    if target.predecessor is not None and not target.predecessor.complete:
        return "already on this worktree's branch — nothing to check out"
    return get_code_host().checkout_task_branch(target.branch, target.pr, target.entry_pr)


def check_out(target: TaskCheckout) -> str:
    """Put a clean working tree on ``target``'s branch and return what the host
    did. Shared by `pdlc checkout` and `pdlc post implement`, which leaves the
    tree at the top of the stack."""
    if working_tree_dirty():
        raise PdlcError(
            "the working tree has uncommitted changes; commit or stash them before "
            f"checking out {target.branch}"
        )
    return _action(target)


def checkout(ref: str) -> str:
    target = resolve_task_checkout(ref)
    action = check_out(target)
    return "\n".join([target.task["title"], f"branch: {target.branch}", action]) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(args):
        print_help(__doc__)
        return 0
    if len(args) != 1 or args[0].startswith("-"):
        print("usage: pdlc checkout DELIVERY_TASK", file=sys.stderr)
        return 1

    try:
        set_recovery(Recovery(
            check=f"pdlc inspect task {args[0]}",
            landed="its branch is the current branch (`git branch --show-current`)",
        ))
        sys.stdout.write(checkout(args[0]))
    except PdlcError as error:
        return report_failure(error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
