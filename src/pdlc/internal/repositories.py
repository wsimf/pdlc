"""Which repository a delivery task belongs to, and the local folder it is worked in.

A task names its repository on a `**Repository:** owner/name` body line;
without one it belongs to the configured code repository. Every repository is
worked in exactly one folder: the code repository in the current checkout, any
other in the clone the home-only `[code.github.checkouts]` table maps it to.
Nothing is inferred from folder names or remotes beyond that; a repository
with no folder is refused rather than guessed.

`in_task_repository` is how a command runs a task's Git and stack calls: every
subprocess inside the block runs in that task's folder (see `internal.workdir`).
"""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from pdlc.config import get_config, repository_root
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.task_artifact import declared_repository
from pdlc.internal.workdir import in_directory


def task_repository(task: Mapping[str, Any]) -> str:
    """The casefolded `owner/name` ``task`` belongs to: its own
    **Repository:** line, else the configured code repository ("" for a code
    provider without repositories)."""
    declared = declared_repository(task.get("body") or "")
    return declared.casefold() if declared else get_config().pull_request_repository()


def is_code_repository(repository: str) -> bool:
    """Whether ``repository`` is the configured code repository, i.e. the one
    worked in the current checkout. An empty name (a pull request registered
    without its repository) means the code repository."""
    return not repository or repository.casefold() == get_config().pull_request_repository()


def repository_folder(repository: str) -> Path | None:
    """The folder ``repository`` is worked in: None for the code repository
    (the current checkout, so subprocesses keep the process's own directory),
    else its `[code.github.checkouts]` clone. Refuses a repository with no
    folder, or a mapped folder that is not there."""
    if is_code_repository(repository):
        return None
    configured = get_config().code_checkouts.get(repository.casefold())
    if not configured:
        raise PdlcError(
            f"no local checkout is configured for {repository}; map it in ~/.pdlc/config.toml under "
            f'[code.github.checkouts] as "{repository}" = "/path/to/its/clone"'
        )
    folder = Path(configured).expanduser()
    if not folder.is_dir():
        raise PdlcError(f"the checkout configured for {repository} under [code.github.checkouts] does not exist: {folder}")
    return folder.resolve()


def repository_path(repository: str) -> Path:
    """The absolute folder ``repository`` is worked in, for display."""
    return repository_folder(repository) or repository_root()


@contextmanager
def in_repository(repository: str) -> Iterator[None]:
    """Run every `git` / `gh` subprocess inside the block in ``repository``'s folder."""
    with in_directory(repository.casefold(), repository_folder(repository)):
        yield


def in_task_repository(task: Mapping[str, Any]) -> AbstractContextManager[None]:
    """`in_repository` for the repository ``task`` belongs to."""
    return in_repository(task_repository(task))


def repository_lines(task: Mapping[str, Any]) -> list[str]:
    """`repository:` and `path:` lines for a task in another repository than
    the code repository, telling the agent which folder to work in; none for
    a code-repository task, whose folder is the current checkout."""
    repository = task_repository(task)
    if is_code_repository(repository):
        return []
    return [f"repository: {repository}", f"path: {repository_path(repository)}"]
