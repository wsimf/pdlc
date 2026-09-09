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

DEFAULT_WORKTREE_ROOT = "~/.pdlc/worktrees"


def worktree_root(configured: str | None) -> str:
    """The configured `worktree.root`, or the `~/.pdlc/worktrees` default when
    the slot is unset. Kept here so `prepare` and `cleanup` agree on it."""
    return configured or DEFAULT_WORKTREE_ROOT


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


def worktree_registered(path: Path) -> bool:
    """True when ``path`` is a worktree of this repo, per ``git worktree list``."""
    listing = _git(["worktree", "list", "--porcelain"])
    registered = {
        Path(line[len("worktree ") :]).resolve()
        for line in listing.splitlines()
        if line.startswith("worktree ")
    }
    return path.resolve() in registered


def existing_worktree(path: Path) -> bool:
    """True when ``path`` is already registered as a worktree of this repo.
    Raises when the directory exists but is not a worktree — the driver must
    clear it themselves rather than have ``prepare`` clobber it."""
    if worktree_registered(path):
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


def branch_exists(branch: str) -> bool:
    return subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        capture_output=True,
    ).returncode == 0


def create_worktree(path: Path, branch: str, base_ref: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if branch_exists(branch):
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


# --- cleanup (pdlc cleanup) ---

def stack_branches(slug: str) -> list[str]:
    """Every local `gh stack` task branch for ``slug`` — the deterministic
    `pdlc/<slug>/<task-id>` names from `pdlc.internal.stack.task_branch_name`."""
    if not slug:
        return []
    listing = _git(
        ["for-each-ref", "--format=%(refname:short)", f"refs/heads/pdlc/{slug}/"]
    )
    return [line for line in listing.splitlines() if line.strip()]


def remove_worktree(path: Path) -> None:
    """Remove a prepared worktree and prune its admin entry. ``--force`` because
    a completed tree still carries build artefacts (node_modules, target/…) that
    would otherwise block removal; the record is verified Complete before this
    runs. A path that is not a registered worktree is left untouched."""
    if not worktree_registered(path):
        if path.exists():
            raise PdlcError(f"{path} exists but is not a Git worktree; remove it yourself")
        return
    _git(["worktree", "remove", "--force", str(path)])
    _git(["worktree", "prune"])


def delete_branch(branch: str) -> None:
    if branch_exists(branch):
        _git(["branch", "-D", branch])
