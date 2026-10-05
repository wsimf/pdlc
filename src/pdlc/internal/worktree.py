"""Local-Git plumbing for the human-only ``pdlc prepare`` / ``pdlc cleanup``
commands, and the best-effort merged-branch pruning ``pdlc post complete``
runs.

``prepare`` scaffolds a dedicated Git worktree for one work item so an agent
can run the PDLC loop in it without disturbing the driver's main checkout. The
work item token is opaque here: it is never resolved or validated against a
backend, only sanitised into a path and branch segment. A ``--after``
predecessor is stored in the worktree's own Git config for ``pdlc inspect
implement`` to stack on.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.trace import record_external_call
from pdlc.internal.workdir import working_directory


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
    record_external_call("git", ["git", *args])
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=cwd or working_directory()
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


def working_tree_dirty() -> bool:
    """Whether the current checkout has staged or unstaged changes. Untracked
    files do not count: they survive a branch switch untouched. False outside a
    Git checkout, where there is no tree to protect."""
    try:
        return bool(_git(["status", "--porcelain", "--untracked-files=no"]))
    except (PdlcError, OSError):
        return False


def current_branch() -> str:
    """The checked-out branch; "" when HEAD is detached or outside a checkout."""
    try:
        return _git(["branch", "--show-current"])
    except (PdlcError, OSError):
        return ""


def stash_changes(message: str) -> None:
    """Set every uncommitted change aside, untracked files included."""
    _git(["stash", "push", "--include-untracked", "--message", message])


def restore_stash() -> None:
    """Re-apply and drop the newest stash; on a conflict Git keeps the stash."""
    _git(["stash", "pop"])


def branch_exists(branch: str) -> bool:
    args = ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"]
    record_external_call("git", args)
    return subprocess.run(args, capture_output=True, cwd=working_directory()).returncode == 0


def create_worktree(path: Path, branch: str, base_ref: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if branch_exists(branch):
        _git(["worktree", "add", str(path), branch])
    else:
        _git(["worktree", "add", "-b", branch, str(path), base_ref])


def fetch_remote_branch(branch: str, remote: str = "origin") -> str | None:
    """``<remote>/<branch>`` once fetched, or None when the remote or branch is
    unavailable."""
    try:
        _git(["fetch", remote, f"{branch}:refs/remotes/{remote}/{branch}"])
    except PdlcError:
        return None
    return f"{remote}/{branch}"


# --- stacking predecessor (pdlc prepare --after / pdlc inspect implement) ---

_AFTER_KEY = "pdlc.after"


def set_worktree_after(path: Path, workitem: str) -> None:
    """Record in ``path``'s own worktree config that its work item stacks after
    ``workitem``. Local only: git config is never pushed.

    Per-worktree config needs the repo-wide ``extensions.worktreeConfig``, which
    is switched on the first time. Git requires ``core.bare``/``core.worktree``
    to move out of the shared config before that, so a repo that sets either is
    refused rather than silently reconfigured."""
    enabled = _config_value(["--bool", "extensions.worktreeConfig"])
    if enabled != "true":
        if _config_value(["--local", "--bool", "core.bare"]) == "true" or _config_value(["--local", "core.worktree"]):
            raise PdlcError(
                "cannot enable extensions.worktreeConfig: core.bare or core.worktree is set in "
                "the shared .git/config; move it to the main worktree's config.worktree first"
            )
        _git(["config", "extensions.worktreeConfig", "true"])
    _git(["config", "--worktree", _AFTER_KEY, sanitize_workitem(workitem)], cwd=path)


def worktree_after() -> str | None:
    """The work item the current worktree stacks after, if it was prepared with
    ``--after``; None outside a Git checkout or when unset."""
    return _config_value([_AFTER_KEY]) or None


def _config_value(args: list[str]) -> str:
    try:
        return _git(["config", "--get", *args])
    except (PdlcError, OSError):
        return ""


def run_init_script(path: Path, script: str) -> None:
    """Run the configured init script as a shell snippet in the new worktree.
    Output is inherited so the driver sees it live; a non-zero exit is raised
    (the worktree still exists and is reported)."""
    record_external_call("sh", ["sh", "-c", script])
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


# --- merged branch pruning (pdlc post complete) ---

def _checked_out_branches() -> set[str]:
    """Every branch checked out in any worktree of this repo."""
    listing = _git(["worktree", "list", "--porcelain"])
    return {line.removeprefix("branch refs/heads/") for line in listing.splitlines() if line.startswith("branch refs/heads/")}


def _leave_branch() -> None:
    """Move HEAD off the current branch so it can be deleted: onto the local
    default branch when it is free, else detached at the default base ref
    (the local default is usually checked out in the driver's main tree)."""
    base = default_base_ref()
    local = base.split("/", 1)[1] if "/" in base else ""
    if local and branch_exists(local):
        try:
            _git(["switch", "--quiet", local])
            return
        except PdlcError:
            pass
    _git(["switch", "--quiet", "--detach", base])


def prune_merged_branches(pull_requests: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Best-effort: force-delete the local branch of every merged PR (a
    `PullRequest` dict) whose tip still equals the PR's head commit, so
    nothing unmerged is lost. When HEAD is on one of those branches and the
    tree is clean, it is moved off first.
    Local only — no fetch, push, or remote delete — and never raises; each
    branch not deleted is reported with a reason.

    Returns {"deleted": [branch], "skipped": [{"branch", "reason"}]}."""
    deleted: list[str] = []
    skipped: list[dict[str, str]] = []
    merged = {pr["branch"]: pr.get("headSha") or "" for pr in pull_requests if pr["state"] == "MERGED" and pr["branch"]}
    try:
        _git(["rev-parse", "--git-dir"])
        eligible: list[str] = []
        for branch, sha in merged.items():
            if not branch_exists(branch):
                skipped.append({"branch": branch, "reason": "missing"})
            elif not sha:
                skipped.append({"branch": branch, "reason": "sha-unknown"})
            elif _git(["rev-parse", f"refs/heads/{branch}"]) != sha:
                skipped.append({"branch": branch, "reason": "sha-mismatch"})
            else:
                eligible.append(branch)

        current = _git(["branch", "--show-current"])
        if current in eligible:
            if _git(["status", "--porcelain"]):
                eligible.remove(current)
                skipped.append({"branch": current, "reason": "dirty-tree"})
            else:
                try:
                    _leave_branch()
                except PdlcError:
                    eligible.remove(current)
                    skipped.append({"branch": current, "reason": "switch-failed"})

        checked_out = _checked_out_branches()
        for branch in eligible:
            if branch in checked_out:
                skipped.append({"branch": branch, "reason": "checked-out-elsewhere"})
                continue
            try:
                _git(["branch", "-D", branch])
                deleted.append(branch)
            except PdlcError:
                skipped.append({"branch": branch, "reason": "delete-failed"})
    except (PdlcError, OSError):
        # Not a Git checkout, or git itself is unavailable: nothing more to do.
        done = set(deleted) | {entry["branch"] for entry in skipped}
        skipped.extend({"branch": branch, "reason": "git-unavailable"} for branch in merged if branch not in done)
    return {"deleted": deleted, "skipped": skipped}
