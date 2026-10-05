"""Selects the configured tracker provider."""

from __future__ import annotations

from pdlc.config import get_config
from pdlc.hosts.workitem_host.base import WorkItemBackend

_instance: WorkItemBackend | None = None


def get_backend() -> WorkItemBackend:
    global _instance
    if _instance is None:
        name = get_config().tracker_provider or "github"
        if name == "github":
            from pdlc.hosts.github_provider import GitHubWorkItemBackend

            _instance = GitHubWorkItemBackend()
        elif name == "azure":
            from pdlc.hosts.azure_provider import AzureWorkItemBackend

            _instance = AzureWorkItemBackend()
        elif name == "file":
            from pdlc.hosts.file_provider import FileWorkItemBackend

            _instance = FileWorkItemBackend()
        else:
            raise RuntimeError(f"unknown [tracker] provider: {name!r}")
    return _instance


def reset_backend() -> None:
    global _instance
    _instance = None
