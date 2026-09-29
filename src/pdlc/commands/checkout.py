#!/usr/bin/env python3
"""NAME
    pdlc checkout - put the working tree on one delivery task's branch

USAGE
    - if the working tree is clean, or holds only this task's own work on its branch:
        pdlc checkout DELIVERY_TASK
    - if the working tree holds uncommitted changes that belong to this task,
      made on another branch:
        pdlc checkout DELIVERY_TASK --carry-changes

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

    When the current branch already is the task's branch, the command reports
    that and changes nothing, whether or not the working tree holds uncommitted
    changes. For the first task of a worktree prepared with `pdlc prepare
    --after`, the worktree's current branch already is that branch too, so the
    command reports that and changes nothing.

    Otherwise uncommitted changes to tracked files stop the checkout, and
    nothing is touched:

        pdlc: the working tree has uncommitted changes on pdlc/record-142/task-003,
        not on this task's branch pdlc/record-142/task-004; nothing was checked out.
        Follow `pdlc guide uncommitted-changes` to carry them onto this task or set
        them aside, then run pdlc checkout again.

    With `--carry-changes` the uncommitted changes, untracked files included,
    are set aside, the task's branch is checked out, and the changes are
    re-applied on it. If the checkout fails, they are re-applied on the branch
    they came from. If they conflict with the task's branch, the command fails
    with the conflicts in the tree and the changes still kept in the stash it
    names.

    On success it prints the task, the branch, and what the host did:

        WORK-142-TASK-004 [UI] Route profile chart
        branch: pdlc/record-142/task-004
        checked out pdlc/record-142/task-004 from its pull request #151

FLAGS
    --carry-changes         bring the working tree's uncommitted changes onto
                            the task's branch instead of refusing

EXAMPLES
    pdlc checkout WORK-142-TASK-004
    pdlc checkout 51
    pdlc checkout WORK-142-TASK-004 --carry-changes
"""

from __future__ import annotations

import sys

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.code_host import get_code_host
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.stack import TaskCheckout, resolve_task_checkout
from pdlc.internal.worktree import current_branch, restore_stash, stash_changes, working_tree_dirty
from pdlc.internal.failure import Recovery, report_failure, set_recovery


def _action(target: TaskCheckout) -> str:
    # Before its own PR exists, a `prepare --after` worktree's first task stays
    # on the prepared branch; the predecessor may be checked out elsewhere.
    # A registered PR instead restores that task's stack.
    if target.pr is None and target.predecessor is not None and not target.predecessor.complete:
        return "already on this worktree's branch — nothing to check out"
    return get_code_host().checkout_task_branch(target.branch, target.pr, target.entry_pr)


def check_out(target: TaskCheckout) -> str:
    """Put a clean working tree on ``target``'s branch and return what the host
    did. Used by `pdlc post implement` to leave the tree at the top of the
    stack; `pdlc checkout` itself also accepts a tree already on the branch."""
    if working_tree_dirty():
        raise PdlcError(
            "the working tree has uncommitted changes; commit or stash them before "
            f"checking out {target.branch}"
        )
    return _action(target)


def _carry(target: TaskCheckout, source: str) -> str:
    """Check ``target`` out with the tree's uncommitted changes brought along.

    The changes go into a named stash first, so a failed checkout can put them
    back where they were and a conflicting re-apply leaves them recoverable."""
    stash = f"pdlc: carried from {source or 'a detached HEAD'} to {target.branch}"
    stash_changes(stash)
    try:
        action = _action(target)
    except PdlcError as error:
        # Re-applied where they came from, the tree is as it was, so the
        # checkout's own error (and its retry semantics) stands unchanged.
        try:
            restore_stash()
        except PdlcError:
            raise PdlcError(
                f"{error}; the uncommitted changes are kept in the stash `{stash}` (`git stash list`)"
            ) from None
        raise
    try:
        restore_stash()
    except PdlcError as error:
        raise PdlcError(
            f"checked out {target.branch}, but the carried changes conflict with it: {error}. "
            f"They are still kept in the stash `{stash}` (`git stash list`); resolve the conflicts in "
            "the tree, then `git stash drop` that stash"
        ) from None
    return f"{action}, carrying the uncommitted changes from {source}"


def checkout(ref: str, carry: bool = False) -> str:
    target = resolve_task_checkout(ref)
    source = current_branch()
    if source == target.branch:
        action = f"already on {target.branch} — nothing to check out"
    elif not working_tree_dirty():
        action = _action(target)
    elif carry:
        action = _carry(target, source)
    else:
        raise PdlcError(
            f"the working tree has uncommitted changes on {source or 'a detached HEAD'}, not on this "
            f"task's branch {target.branch}; nothing was checked out.\n"
            "Follow `pdlc guide uncommitted-changes` to carry them onto this task or set them aside, "
            "then run pdlc checkout again."
        )
    return "\n".join([target.task["title"], f"branch: {target.branch}", action]) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(args):
        print_help(__doc__)
        return 0
    carry = "--carry-changes" in args
    args = [arg for arg in args if arg != "--carry-changes"]
    if len(args) != 1 or args[0].startswith("-"):
        print("usage: pdlc checkout DELIVERY_TASK [--carry-changes]", file=sys.stderr)
        return 1

    try:
        set_recovery(Recovery(
            check=f"pdlc inspect task {args[0]}",
            landed="its branch is the current branch (`git branch --show-current`)",
        ))
        sys.stdout.write(checkout(args[0], carry))
    except PdlcError as error:
        return report_failure(error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
