"""Selects the work-item host. `PDLC_BACKEND` defaults to "github"; "file"
uses a local directory tree (see workitem_host/file.py)."""

from __future__ import annotations

import os

from workitem_host.base import WorkItemBackend

_instance: WorkItemBackend | None = None


def get_backend() -> WorkItemBackend:
    global _instance
    if _instance is None:
        name = os.environ.get("PDLC_BACKEND", "github")
        if name == "github":
            from workitem_host.github import GitHubWorkItemBackend

            _instance = GitHubWorkItemBackend()
        elif name == "file":
            from workitem_host.file import FileWorkItemBackend

            _instance = FileWorkItemBackend()
        else:
            raise RuntimeError(f"unknown PDLC_BACKEND: {name!r}")
    return _instance


def reset_backend() -> None:
    """Test hook: drop the cached backend so the next call re-reads env."""
    global _instance
    _instance = None
