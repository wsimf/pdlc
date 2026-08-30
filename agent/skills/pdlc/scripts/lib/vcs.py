"""Local-Git helpers shared by the verification-freshness checks.

A delivery task is exactly one commit touching only its own files, so a
`(Verified @ <commit>)` anchor's own diff against `HEAD` is what decides
whether the evidence that cited it still holds. Both `pdlc-inspect-verify.py`
and `pdlc-inspect-complete.py` (and completion's own readiness check) reuse
this so the audit-time and lock-time passes can never drift apart.
"""

from __future__ import annotations

import subprocess

from pdlc_common import PdlcError


def files_touched_by(commit: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PdlcError(result.stderr.strip() or f"git diff-tree failed for {commit}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def is_stale(commit: str, files: list[str]) -> bool:
    """True when anything has touched `files` between `commit` and `HEAD`, or
    when the commit is unknown / touched nothing (nothing to trust)."""
    if not files:
        return True
    result = subprocess.run(
        ["git", "log", "--oneline", f"{commit}..HEAD", "--", *files],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PdlcError(result.stderr.strip() or f"git log failed for {commit}")
    return bool(result.stdout.strip())


def stale_commits(commits: list[str]) -> set[str]:
    """The subset of `commits` whose evidence no longer holds against HEAD. An
    unknown or unreadable commit counts as stale — completion must not lock on
    an anchor it cannot verify."""
    verdict: dict[str, bool] = {}
    for commit in commits:
        if commit in verdict:
            continue
        try:
            verdict[commit] = is_stale(commit, files_touched_by(commit))
        except PdlcError:
            verdict[commit] = True
    return {commit for commit, stale in verdict.items() if stale}
