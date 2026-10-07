"""Private, per-work-item files that CLI commands print for agents to read."""

from __future__ import annotations

import ntpath
import os
import posixpath
import secrets
import tempfile
from pathlib import Path

from pdlc.config import get_config, project_root
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.workitem import ref_label

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _safe_component(name: str) -> str:
    """Refuse a path component that could escape its work-item directory."""
    rejected = (
        not name
        or name in (".", "..")
        or ":" in name
        or any(flavour.basename(name) != name for flavour in (posixpath, ntpath))
    )
    if rejected:
        raise PdlcError(f"refusing cache path component: {name!r}")
    return name


def cache_directory(work_item: str) -> Path:
    """Resolve `.pdlc/cache/<workitem>` from the configured location."""
    setting = get_config().cache_root
    if setting == "repository_default":
        base = project_root()
    elif setting == "global_default":
        base = Path.home()
    else:
        if not setting.strip():
            raise PdlcError("[cache] root must be a directory or a named default")
        configured = Path(setting).expanduser()
        base = configured if configured.is_absolute() else project_root() / configured
    return base / ".pdlc" / "cache" / _safe_component(str(work_item))


def scratch_path(work_item: str, name: str, suffix: str = ".md") -> Path:
    """Return a path with a random suffix for a CLI-generated file."""
    if suffix not in (".md", ".json"):
        raise PdlcError(f"unsupported cache file suffix: {suffix!r}")
    return cache_directory(work_item) / f"{_safe_component(ref_label())}-{_safe_component(name)}-{secrets.token_hex(3)}{suffix}"


def cache_file(work_item: str, name: str, suffix: str = ".json") -> Path:
    """Return the fixed path of a CLI-owned file that is rewritten in place."""
    if suffix not in (".md", ".json"):
        raise PdlcError(f"unsupported cache file suffix: {suffix!r}")
    return cache_directory(work_item) / f"{_safe_component(ref_label())}-{_safe_component(name)}{suffix}"


def _cache_parent(path: Path) -> None:
    directory = path.parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for component in (directory.parent.parent, directory.parent, directory):
        if component.is_symlink():
            raise PdlcError(f"refusing symlinked cache directory: {component}")


def replace_cache_file(path: Path, text: str) -> Path:
    """Atomically replace a fixed cache file, restricted to its owner."""
    _cache_parent(path)
    return replace_file(path, text)


def replace_file(path: Path, text: str) -> Path:
    """Atomically replace a file, so a crash never leaves it half written."""
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=path.suffix, dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def write_scratch(path: Path, text: str) -> Path:
    """Create the cache file exclusively and restrict it to its owner."""
    _cache_parent(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
