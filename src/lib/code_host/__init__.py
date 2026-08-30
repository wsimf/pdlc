"""Selects the code host. `PDLC_CODE_HOST` picks it explicitly ("github",
"file", or "none"); otherwise it follows `PDLC_BACKEND` — "github" for the
GitHub work-item backend, "file" for the on-disk store, "none" (no
pull-request linkage) for any other."""

from __future__ import annotations

import os

from code_host.base import CodeHost

_instance: CodeHost | None = None


def _default_name() -> str:
    backend = os.environ.get("PDLC_BACKEND", "github")
    if backend in ("github", "file"):
        return backend
    return "none"


def get_code_host() -> CodeHost:
    global _instance
    if _instance is None:
        name = os.environ.get("PDLC_CODE_HOST") or _default_name()
        if name == "github":
            from code_host.github import GitHubCodeHost

            _instance = GitHubCodeHost()
        elif name == "file":
            from code_host.file import FileCodeHost

            _instance = FileCodeHost()
        elif name == "none":
            from code_host.none import NoneCodeHost

            _instance = NoneCodeHost()
        else:
            raise RuntimeError(f"unknown PDLC_CODE_HOST: {name!r}")
    return _instance


def reset_code_host() -> None:
    """Test hook: drop the cached code host so the next call re-reads env."""
    global _instance
    _instance = None
