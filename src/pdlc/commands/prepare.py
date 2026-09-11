#!/usr/bin/env python3
"""NAME
    pdlc prepare - human-only: scaffold a dedicated Git worktree for one work item

USAGE
    pdlc prepare WORKITEM [--from REF] [--yes]

DESCRIPTION
    Creates `<worktree.root>/<repo-name>/<WORKITEM>` on a new `pdlc/record-<WORKITEM>`
branch, optionally runs the configured `worktree.init_script` in it, and prints
the worktree path — and nothing else — on stdout, so the driver can:

    cd "$(pdlc prepare 142)"

WORKITEM is an opaque token: it is only sanitised into the path and branch, never
resolved or validated against a backend. Re-running for the same WORKITEM is a
no-op that just reprints the path. This command is not part of the agent
workflow and is intentionally absent from `pdlc --help`.

Config (`[worktree]` table, merged from ~/.pdlc/config.toml then .pdlc/config.toml):

    root         parent directory for every prepared worktree
                 (default: ~/.pdlc/worktrees)
    base_ref     ref new branches start from (default: detected default branch)
    init_script  optional shell snippet run in the new worktree after creation
"""

from __future__ import annotations

import sys

from pdlc.config import get_config, repository_root
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help
from pdlc.internal.worktree import (
    branch_name,
    create_worktree,
    default_base_ref,
    existing_worktree,
    fetch_base,
    run_init_script,
    target_path,
    worktree_root,
)


def _parse(argv: list[str]) -> tuple[str, str | None, bool]:
    workitem: str | None = None
    from_ref: str | None = None
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
        elif argument.startswith("-"):
            raise PdlcError(f"unknown option {argument}")
        elif workitem is None:
            workitem = argument
        else:
            raise PdlcError(f"unexpected argument {argument}")
        index += 1
    if workitem is None:
        raise PdlcError("usage: pdlc prepare WORKITEM [--from REF] [--yes]")
    return workitem, from_ref, assume_yes


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


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in args):
        print_help(__doc__)
        return 0

    try:
        workitem, from_ref, assume_yes = _parse(args)
        config = get_config()
        repo = repository_root()
        path = target_path(worktree_root(config.worktree_root), repo.name, workitem)

        if existing_worktree(path):
            print(f"pdlc: worktree already present at {path}", file=sys.stderr)
            print(path)
            return 0

        base_ref = from_ref or config.worktree_base_ref or default_base_ref()
        fetch_base(base_ref)
        create_worktree(path, branch_name(workitem), base_ref)
        print(f"pdlc: created worktree at {path} on {branch_name(workitem)}", file=sys.stderr)

        if config.worktree_init_script and _should_run_script(
            path, config.worktree_init_script, assume_yes
        ):
            run_init_script(path, config.worktree_init_script)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
