"""Scratch files inspectors write for an agent to read back.

These live in the shared temp directory under a name derived from the backing
store and the record, so a re-run overwrites its own file instead of littering.
That predictability is why the write is opened deliberately rather than through
`Path.write_text`: on a multi-user host the name is guessable, so the open must
refuse to follow a symlink planted at that path and must not leave the contents
readable by other users. `pdlc prompt` raises the stakes further — its scratch
file is a brief a sub-agent executes, not data it reads — so anything that can
swap the file between the write and the read is a way to steer that agent.

Those two guarantees rest on POSIX primitives, so what they cost on Windows is
worth stating. `O_NOFOLLOW` is a POSIX-only flag and `os.open`'s mode argument
carries no owner/group/other split there, so both degrade to no-ops. Neither is
load-bearing on Windows: `tempfile.gettempdir()` resolves per-user rather than
to a shared sticky directory, so another account cannot plant the symlink or
read the contents in the first place. `O_CREAT | O_EXCL` maps to `CREATE_NEW`
and keeps the exclusive-create guarantee on every platform.
"""

from __future__ import annotations

import ntpath
import os
import posixpath
import tempfile
from pathlib import Path

from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.workitem import ref_label

# `O_NOFOLLOW` is POSIX-only; on Windows the flag is absent and unnecessary.
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _safe_component(name: str) -> str:
    """Return `name` if it is a single filename, else refuse it.

    Callers build `name` from a work item or task reference, which a backend
    resolves from a project field rather than minting itself, so a separator or
    `..` reaching this point would place the file outside the temp directory.
    Both path flavours are checked so the same name is accepted or refused on
    every platform: `..` and `/` traverse on POSIX and Windows alike, while
    `\\`, a drive prefix, and an alternate-data-stream `:` only bite on Windows.
    """
    rejected = (
        not name
        or name in (".", "..")
        or ":" in name
        or any(flavour.basename(name) != name for flavour in (posixpath, ntpath))
    )
    if rejected:
        raise PdlcError(f"refusing scratch file name outside the temp directory: {name!r}")
    return name


def scratch_path(name: str, suffix: str = ".md") -> Path:
    """The scratch path for `name`, prefixed with the backing store's label.

    Refuses anything but a single safe filename.
    """
    return Path(tempfile.gettempdir()) / f"{ref_label()}-{_safe_component(name)}{suffix}"


def write_scratch(path: Path, text: str) -> Path:
    """Write `text` to `path` as a file this run created, owner-readable only.

    The previous run's file is removed and the new one created exclusively, so
    the contents can never land in a file, or through a symlink, that something
    else put there first: on a sticky temp directory that unlink fails for a
    path we do not own, and the write stops rather than following it. A symlink
    planted in the window between the two fails the open instead of redirecting
    it, because `O_CREAT | O_EXCL` refuses an existing path without resolving it.
    """
    path.unlink(missing_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
