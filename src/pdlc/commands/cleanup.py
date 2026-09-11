#!/usr/bin/env python3
"""NAME
    pdlc cleanup - human-only: tear down the local scaffolding for a completed work item

USAGE
    pdlc cleanup WORKITEM [--yes]

DESCRIPTION
    Resolves WORKITEM against the backend and refuses unless it is locked at
    Complete. Then removes the worktree at `<worktree.root>/<repo-name>/<WORKITEM>`
    and force-deletes its local branches — the `pdlc/record-<WORKITEM>` base branch
    and every `pdlc/<slug>/<task-id>` branch `gh stack` created. Remote branches and
    merged pull requests are left to GitHub.

    This is the counterpart of `pdlc prepare`: local-only teardown, off the agent
    workflow, and absent from `pdlc --help`. It needs the backend only to confirm
    the work item is complete.
"""

from __future__ import annotations

import sys

from pdlc.config import get_config, repository_root
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import item_slug, item_status, item_gate
from pdlc.domain.workflow import Lifecycle
from pdlc.internal.inputs import print_help
from pdlc.internal.workitem import resolve_item, workflow_for_item
from pdlc.internal.worktree import (
    branch_name,
    delete_branch,
    remove_worktree,
    stack_branches,
    target_path,
    worktree_root,
)


def _parse(argv: list[str]) -> tuple[str, bool]:
    workitem: str | None = None
    assume_yes = False
    for argument in argv:
        if argument == "--yes":
            assume_yes = True
        elif argument.startswith("-"):
            raise PdlcError(f"unknown option {argument}")
        elif workitem is None:
            workitem = argument
        else:
            raise PdlcError(f"unexpected argument {argument}")
    if workitem is None:
        raise PdlcError("usage: pdlc cleanup WORKITEM [--yes]")
    return workitem, assume_yes


def _require_complete(workitem: str) -> dict:
    record = resolve_item(workitem)
    pipeline, state = workflow_for_item(record)
    if not (state.stage == pipeline.terminal_stage and state.lifecycle == Lifecycle.COMPLETED):
        raise PdlcError(
            f"work item {workitem} is at {item_status(record)} / {item_gate(record)}, "
            f"not Complete; refusing to clean up"
        )
    return record


def _confirm(path, branches: list[str], assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        raise PdlcError("not a TTY; re-run with --yes to confirm the teardown")
    listed = "\n".join(f"  - {branch}" for branch in branches) or "  (none)"
    print(
        f"Remove worktree:\n  {path}\n\nForce-delete local branches:\n{listed}\n",
        file=sys.stderr,
    )
    return input("[y/N] ").strip().lower() in {"y", "yes"}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in args):
        print_help(__doc__)
        return 0

    try:
        workitem, assume_yes = _parse(args)
        config = get_config()
        repo = repository_root()
        record = _require_complete(workitem)

        path = target_path(worktree_root(config.worktree_root), repo.name, workitem)
        branches = [branch_name(workitem), *stack_branches(item_slug(record))]

        if not _confirm(path, branches, assume_yes):
            print("pdlc: aborted", file=sys.stderr)
            return 1

        # Worktree first: a branch checked out in a worktree cannot be deleted.
        remove_worktree(path)
        for branch in branches:
            delete_branch(branch)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(f"pdlc: cleaned up worktree and {len(branches)} branch(es) for {workitem}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
