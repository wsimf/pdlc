"""Local-Git plumbing for the human-only ``pdlc prepare`` command.

``prepare`` scaffolds a dedicated Git worktree for one work item so an agent
can run the PDLC loop in it without disturbing the driver's main checkout. The
work item token is opaque here: it is never resolved or validated against a
backend, only sanitised into a path and branch segment.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pdlc.domain.lifecycle import PdlcError


_TOKEN = re.compile(r"[A-Za-z0-9._-]+")


def sanitize_workitem(token: str) -> str:
    """The work item token as given, once proven safe to splice into a path and
    a branch name. Rejects anything outside ``[A-Za-z0-9._-]`` (so ``..`` and
    path separators cannot escape the worktree root)."""
    token = token.strip()
    if not token or not _TOKEN.fullmatch(token) or token in {".", ".."}:
        raise PdlcError(
            f"invalid work item {token!r}: use letters, digits, '.', '_' or '-'"
        )
    return token


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=cwd
    )
    if result.returncode != 0:
        raise PdlcError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def target_path(root: str, repo_name: str, workitem: str) -> Path:
    """``<root>/<repo-name>/<workitem>`` with ``~`` expanded."""
    return Path(root).expanduser() / repo_name / sanitize_workitem(workitem)


def branch_name(workitem: str) -> str:
    return f"pdlc/record-{sanitize_workitem(workitem)}"


def default_base_ref() -> str:
    """The repo's default branch as ``<remote>/<branch>``; ``HEAD`` when no
    remote HEAD is known (fresh clone without ``origin/HEAD``, or no remote)."""
    try:
        ref = _git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"])
    except PdlcError:
        return "HEAD"
    return ref or "HEAD"


def existing_worktree(path: Path) -> bool:
    """True when ``path`` is already registered as a worktree of this repo.
    Raises when the directory exists but is not a worktree — the driver must
    clear it themselves rather than have ``prepare`` clobber it."""
    listing = _git(["worktree", "list", "--porcelain"])
    registered = {
        Path(line[len("worktree ") :]).resolve()
        for line in listing.splitlines()
        if line.startswith("worktree ")
    }
    if path.resolve() in registered:
        return True
    if path.exists():
        raise PdlcError(f"{path} already exists and is not a Git worktree")
    return False


def fetch_base(base_ref: str) -> None:
    """Best-effort refresh of a ``<remote>/<branch>`` base so the new branch
    starts from current upstream. A missing remote or offline machine is a
    warning, not a failure."""
    if "/" not in base_ref or base_ref == "HEAD":
        return
    remote, branch = base_ref.split("/", 1)
    try:
        _git(["fetch", remote, branch])
    except PdlcError as error:
        print(f"pdlc: could not fetch {base_ref}: {error}", flush=True)


def create_worktree(path: Path, branch: str, base_ref: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        capture_output=True,
    ).returncode == 0
    if exists:
        _git(["worktree", "add", str(path), branch])
    else:
        _git(["worktree", "add", "-b", branch, str(path), base_ref])


def run_init_script(path: Path, script: str) -> None:
    """Run the configured init script as a shell snippet in the new worktree.
    Output is inherited so the driver sees it live; a non-zero exit is raised
    (the worktree still exists and is reported)."""
    result = subprocess.run(script, shell=True, cwd=path)
    if result.returncode != 0:
        raise PdlcError(
            f"init script failed (exit {result.returncode}); worktree left at {path}"
        )
