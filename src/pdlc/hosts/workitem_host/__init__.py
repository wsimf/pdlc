"""Selects the configured work-item host."""

from __future__ import annotations

import os

from pdlc.hosts.workitem_host.base import WorkItemBackend

_instance: WorkItemBackend | None = None


def get_backend() -> WorkItemBackend:
    global _instance
    if _instance is None:
        name = os.environ.get("PDLC_BACKEND", "github")
        if name == "github":
            from pdlc.hosts.workitem_host.github import GitHubWorkItemBackend

            _instance = GitHubWorkItemBackend()
        elif name == "azure":
            from pdlc.hosts.workitem_host.azure import AzureWorkItemBackend

            _instance = AzureWorkItemBackend()
        elif name == "file":
            from pdlc.hosts.workitem_host.file import FileWorkItemBackend

            _instance = FileWorkItemBackend()
        else:
            raise RuntimeError(f"unknown PDLC_BACKEND: {name!r}")
    return _instance


def reset_backend() -> None:
    global _instance
    _instance = None
