"""Local-Git helpers behind verification freshness.

A verification report records the HEAD it was checked at. Freshness is then a
tree comparison — which files differ between that HEAD and now — rather than
commit ancestry, so a rebase or restack that leaves a task's files untouched
does not invalidate its evidence. `pdlc inspect verify`, `pdlc post verify`,
and completion all read through these so the audit-time and lock-time passes
can never drift apart.
"""

from __future__ import annotations

import subprocess
from typing import Any

from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.trace import record_external_call

# Record paperwork the file backend may keep in the repository; never code.
_PAPERWORK_PREFIX = ".pdlc/"


def _run_git(args: list[str], **kwargs: Any) -> "subprocess.CompletedProcess[Any]":
    record_external_call("git", ["git", *args])
    return subprocess.run(["git", *args], **kwargs)


def head_commit() -> str:
    result = _run_git(["rev-parse", "HEAD"], capture_output=True, text=True)
    if result.returncode != 0:
        raise PdlcError(result.stderr.strip() or "git rev-parse HEAD failed")
    return result.stdout.strip()


def has_tracked_changes() -> bool:
    """True when tracked files differ from HEAD, so HEAD is not what a check
    of the working tree actually read."""
    result = _run_git(["status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True)
    if result.returncode != 0:
        raise PdlcError(result.stderr.strip() or "git status failed")
    return bool(result.stdout.strip())


def uncommitted_changes() -> str:
    """`git status --short` for the working tree, untracked files included and
    paperwork excluded; "" when it is clean or not a Git checkout."""
    result = _run_git(["status", "--short", "--untracked-files=all"], capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    lines = [line for line in result.stdout.splitlines() if line.strip() and not line[3:].startswith(_PAPERWORK_PREFIX)]
    return "\n".join(lines)


def changed_files(since: str) -> set[str] | None:
    """Files whose content differs between `since` and HEAD, paperwork
    excluded; None when `since` is not a readable commit here."""
    result = _run_git(["diff", "--name-only", since, "HEAD", "--"], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return {line for line in result.stdout.splitlines() if line.strip() and not line.startswith(_PAPERWORK_PREFIX)}


def contains_commit(commit: str) -> bool:
    """True when `commit` exists locally and HEAD includes it."""
    result = _run_git(["merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True)
    return result.returncode == 0


def _show(revisions: str, *flags: str) -> str:
    """One `git show` read over a revision or range, as text."""
    result = _run_git(["show", *flags, revisions, "--"], capture_output=True, text=True)
    if result.returncode != 0:
        raise PdlcError(result.stderr.strip() or f"git show {revisions} failed")
    return result.stdout.strip()


def diff_stat(revisions: str) -> str:
    """The `--stat` summary of a revision or range, for a review's header."""
    return _show(revisions, "--stat", "--oneline")


def diff_text(revisions: str) -> str:
    """The full patch for a revision or range, for a review to read."""
    return _show(revisions)


def touched_files(revisions: str) -> list[str]:
    """Source files a revision or range changed, paperwork excluded."""
    names = _show(revisions, "--name-only", "--format=").splitlines()
    return sorted({
        name.strip() for name in names
        if name.strip() and not name.startswith(_PAPERWORK_PREFIX)
    })
