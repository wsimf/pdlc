"""UTF-8 atomic writes and a fail-fast single-writer boundary for local stores."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import ParamSpec, TypeVar

from pdlc.domain.lifecycle import PdlcError

P = ParamSpec("P")
R = TypeVar("R")


def atomic_write(path: Path, text: str) -> None:
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def single_writer(operation: Callable[P, R]) -> Callable[P, R]:
    @wraps(operation)
    def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
        root = Path(os.environ.get("PDLC_HOME", ".pdlc"))
        root.mkdir(parents=True, exist_ok=True)
        lock = root / ".writer.lock"
        try:
            lock.mkdir()
        except FileExistsError:
            raise PdlcError(
                f"file store is locked: {lock}; if its writer crashed, confirm no writer is running before removing this directory"
            ) from None
        try:
            return operation(*args, **kwargs)
        finally:
            lock.rmdir()
    return guarded
