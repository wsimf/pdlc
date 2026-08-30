"""Selects the configured code host."""

from __future__ import annotations

import os

from pdlc.hosts.code_host.base import CodeHost

_instance: CodeHost | None = None


def _default_name() -> str:
    backend = os.environ.get("PDLC_BACKEND", "github")
    return backend if backend in ("github", "file") else "none"


def get_code_host() -> CodeHost:
    global _instance
    if _instance is None:
        name = os.environ.get("PDLC_CODE_HOST") or _default_name()
        if name == "github":
            from pdlc.hosts.code_host.github import GitHubCodeHost

            _instance = GitHubCodeHost()
        elif name == "file":
            from pdlc.hosts.code_host.file import FileCodeHost

            _instance = FileCodeHost()
        elif name == "none":
            from pdlc.hosts.code_host.none import NoneCodeHost

            _instance = NoneCodeHost()
        else:
            raise RuntimeError(f"unknown PDLC_CODE_HOST: {name!r}")
    return _instance


def reset_code_host() -> None:
    global _instance
    _instance = None
