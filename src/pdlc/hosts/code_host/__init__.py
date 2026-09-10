"""Selects the configured code host."""

from __future__ import annotations

from pdlc.config import default_code_host, get_config
from pdlc.hosts.code_host.base import CodeHost

_instance: CodeHost | None = None


def _default_name() -> str:
    return default_code_host(get_config().backend or "github")


def get_code_host() -> CodeHost:
    global _instance
    if _instance is None:
        name = get_config().code_host or _default_name()
        if name == "github":
            from pdlc.hosts.github_provider import GitHubCodeHost

            _instance = GitHubCodeHost()
        elif name == "file":
            from pdlc.hosts.file_provider import FileCodeHost

            _instance = FileCodeHost()
        elif name == "none":
            from pdlc.hosts.none_provider import NoneCodeHost

            _instance = NoneCodeHost()
        else:
            raise RuntimeError(f"unknown [code_host] name: {name!r}")
    return _instance


def reset_code_host() -> None:
    global _instance
    _instance = None
