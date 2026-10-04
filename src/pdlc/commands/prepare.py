#!/usr/bin/env python3
"""NAME
    pdlc prepare - human-only: scaffold a dedicated Git worktree for one work item

USAGE
    pdlc prepare WORKITEM [--from REF | --after WORKITEM] [--yes]

FLAGS
    --from REF           ref the new branch starts from, overriding `worktree.base_ref`
    --after WORKITEM     stack this worktree's work on WORKITEM's latest implemented task; cannot combine with --from
    --yes                run the configured init script without prompting

DESCRIPTION
    Creates `<worktree.root>/<repo-name>/<WORKITEM>` on a new `pdlc/record-<WORKITEM>`
branch. For a numeric work item with an open registered delivery-task pull request,
it restores the highest task's stack and checks out that task branch. It optionally
runs the configured `worktree.init_script`, and prints
the worktree path — and nothing else — on stdout, so the driver can:

    cd "$(pdlc prepare 142)"

Non-numeric WORKITEM tokens are only sanitised into the path and branch. A
numeric WORKITEM reads its delivery tasks and registered pull requests before
creating a worktree. `--from` uses its explicit ref without restoring a stack.
Re-running for the same WORKITEM checks out the top open task only when the
worktree can switch branches safely. This command is not part of the agent
workflow and is intentionally absent from `pdlc --help`.

`--after WORKITEM` is for work that builds on another, not-yet-merged work item.
Without an open task pull request to restore, the new branch starts from the
predecessor's latest implemented task branch (local, else fetched from
`origin`), so every stage in the worktree sees that code. When the predecessor
is Complete, has no implemented task with a registered pull request, or its
branch cannot be found, the branch starts from the default base instead, with a
note on stderr. Either way the predecessor is recorded in the worktree's own Git
config (`pdlc.after`, enabling `extensions.worktreeConfig` the first time), and
`pdlc inspect implement` run in the worktree stacks the first task onto the
predecessor's latest pull request. The record is local only; re-running with
`--after` on an existing worktree updates it without moving the branch.

Config (`[worktree]` table, merged from home defaults, the matching home
`[repository."owner/name".worktree]` section, then .pdlc/config.toml):

    root         parent directory for every prepared worktree
                 (default: ~/.pdlc/worktrees)
    base_ref     ref new branches start from (default: detected default branch)
    init_script  optional shell snippet run in the new worktree after creation

Repository sections match the checkout's GitHub origin, case-insensitively;
without a recognizable origin, the repository file's code.github.repository
supplies the identity. Existing worktrees do not run the init script again.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path

from pdlc.domain.records import pull_ref
from pdlc.config import get_config, repository_root
from pdlc.commands.checkout import checkout
from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.code_host import get_code_host
from pdlc.internal.inputs import print_help
from pdlc.internal.stack import resolve_predecessor
from pdlc.internal.workitem import task_tree
from pdlc.internal.worktree import (
    branch_exists,
    branch_name,
    create_worktree,
    default_base_ref,
    existing_worktree,
    fetch_base,
    fetch_remote_branch,
    run_init_script,
    set_worktree_after,
    target_path,
    worktree_root,
)
from pdlc.internal.failure import report_failure


def _parse(argv: list[str]) -> tuple[str, str | None, str | None, bool]:
    workitem: str | None = None
    from_ref: str | None = None
    after: str | None = None
    assume_yes = False
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--yes":
            assume_yes = True
        elif argument == "--from":
            if index + 1 >= len(argv):
                raise PdlcError("--from requires a ref")
            from_ref = argv[index + 1]
            index += 1
        elif argument == "--after":
            if index + 1 >= len(argv):
                raise PdlcError("--after requires a work item")
            after = argv[index + 1]
            index += 1
        elif argument.startswith("-"):
            raise PdlcError(f"unknown option {argument}")
        elif workitem is None:
            workitem = argument
        else:
            raise PdlcError(f"unexpected argument {argument}")
        index += 1
    if workitem is None:
        raise PdlcError("usage: pdlc prepare WORKITEM [--from REF | --after WORKITEM] [--yes]")
    if from_ref and after:
        raise PdlcError("--from and --after cannot be combined")
    return workitem, from_ref, after, assume_yes


def _after_base(after: str) -> str | None:
    """The ref a worktree prepared ``--after`` starts from: the predecessor's
    latest implemented task branch, or None to fall back to the default base."""
    predecessor = resolve_predecessor(after)
    if predecessor.complete:
        print(f"pdlc: work item {after} is Complete; starting from the default base", file=sys.stderr)
        return None
    if predecessor.branch is None:
        print(
            f"pdlc: work item {after} has no implemented task with a registered pull request yet; "
            "starting from the default base",
            file=sys.stderr,
        )
        return None
    if branch_exists(predecessor.branch):
        return predecessor.branch
    remote = fetch_remote_branch(predecessor.branch)
    if remote is None:
        print(f"pdlc: branch {predecessor.branch} not found; starting from the default base", file=sys.stderr)
    return remote


def _should_run_script(path, script: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print(
            "pdlc: skipping init script (not a TTY); re-run with --yes to run it",
            file=sys.stderr,
        )
        return False
    print(f"Run init script in {path}?\n\n  {script}\n", file=sys.stderr)
    return input("[y/N] ").strip().lower() in {"y", "yes"}


def _resume_task(workitem: str) -> str | None:
    """The highest task whose current registered PR is open, if any."""
    if not workitem.isdecimal():
        return None
    tasks = [task for task in task_tree(workitem) if task.get("taskId") and task.get("prs")]
    refs = sorted({ref for task in tasks for ref in task["prs"]})
    if not refs:
        return None
    prs = {pull_ref(pr): pr for pr in get_code_host().pull_requests(refs)}
    if set(prs) != set(refs):
        raise PdlcError("code host returned fewer pull requests than the task registry; refusing to prepare")
    open_tasks = [task for task in tasks if prs[max(task["prs"])]["state"] == "OPEN"]
    return max(open_tasks, key=lambda task: task["number"])["title"] if open_tasks else None


@contextmanager
def _in_worktree(path: Path):
    previous = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(previous)


def _restore_stack(path: Path, task: str | None) -> None:
    if task is None:
        return
    try:
        with _in_worktree(path):
            action = checkout(task)
    except PdlcError as error:
        raise PdlcError(f"worktree is at {path}, but its task stack could not be restored: {error}") from error
    print(f"pdlc: {action.strip()}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in args):
        print_help(__doc__)
        return 0

    try:
        workitem, from_ref, after, assume_yes = _parse(args)
        config = get_config()
        repo = repository_root()
        path = target_path(worktree_root(config.worktree_root), repo.name, workitem)
        resume_task = _resume_task(workitem) if from_ref is None else None

        if existing_worktree(path):
            if after:
                set_worktree_after(path, after)
            _restore_stack(path, resume_task)
            print(f"pdlc: worktree already present at {path}", file=sys.stderr)
            print(path)
            return 0

        after_ref = _after_base(after) if after and resume_task is None else None
        base_ref = from_ref or after_ref or config.worktree_base_ref or default_base_ref()
        if after_ref is None:
            fetch_base(base_ref)
        create_worktree(path, branch_name(workitem), base_ref)
        if after:
            set_worktree_after(path, after)
        print(f"pdlc: created worktree at {path} on {branch_name(workitem)} from {base_ref}", file=sys.stderr)

        _restore_stack(path, resume_task)

        if config.worktree_init_script and _should_run_script(
            path, config.worktree_init_script, assume_yes
        ):
            run_init_script(path, config.worktree_init_script)
    except PdlcError as error:
        return report_failure(error)

    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
