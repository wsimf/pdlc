"""The repository, and its folder, every `git` / `gh` subprocess runs against.

A delivery task may belong to another repository than the checkout `pdlc` was
started in, so the command routes its Git and stack calls to that
repository's own folder (see `internal.repositories`). Every subprocess seam —
`hosts.lib.process.run_process`, `internal.vcs`, `internal.worktree` — reads
`working_directory()` as its `cwd`; None keeps the process's own directory,
which is every single-repository run. A code host reads `working_repository()`
to qualify what a cwd-bound call (`gh stack view`) reports.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator

# (repository, folder); None outside any `in_directory` block.
_current: ContextVar[tuple[str, Path | None] | None] = ContextVar("pdlc_working_directory", default=None)


def working_directory() -> Path | None:
    """The folder subprocesses run in, or None for the process's own."""
    current = _current.get()
    return current[1] if current else None


def working_repository() -> str | None:
    """The casefolded `owner/name` subprocesses act on, or None when no block
    named one (the configured code repository)."""
    current = _current.get()
    return current[0] if current else None


@contextmanager
def in_directory(repository: str, path: Path | None) -> Iterator[None]:
    """Run every subprocess inside the block against ``repository`` in
    ``path``; a None path keeps the process's own directory."""
    token = _current.set((repository, path))
    try:
        yield
    finally:
        _current.reset(token)
