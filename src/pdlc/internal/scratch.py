"""Scratch files inspectors write for an agent to read back.

These live in the shared temp directory under a name derived from the backing
store and the record, so a re-run overwrites its own file instead of littering.
That predictability is why the write is opened deliberately rather than through
`Path.write_text`: on a multi-user host the name is guessable, so the open must
refuse to follow a symlink planted at that path and must not leave the contents
readable by other users. `pdlc prompt` raises the stakes further — its scratch
file is a brief a sub-agent executes, not data it reads — so anything that can
swap the file between the write and the read is a way to steer that agent.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pdlc.internal.workitem import ref_label


def scratch_path(name: str, suffix: str = ".md") -> Path:
    """The scratch path for `name`, prefixed with the backing store's label."""
    return Path(tempfile.gettempdir()) / f"{ref_label()}-{name}{suffix}"


def write_scratch(path: Path, text: str) -> Path:
    """Write `text` to `path` as a file this run created, owner-readable only.

    The previous run's file is removed and the new one created exclusively, so
    the contents can never land in a file, or through a symlink, that something
    else put there first: on a sticky temp directory that unlink fails for a
    path we do not own, and the write stops rather than following it.
    """
    path.unlink(missing_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
