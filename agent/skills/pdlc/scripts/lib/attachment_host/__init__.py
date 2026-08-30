"""Selects the PDLC attachment host.

``PDLC_ATTACHMENT_HOST`` defaults to ``file`` and stores attachments under
``$PDLC_HOME/<work-item-number>/attachments`` (with ``$PDLC_HOME`` defaulting
to ``.pdlc``). Set it to ``none`` when a caller must fail explicitly instead
of creating local artifacts.
"""

from __future__ import annotations

import os
from pathlib import Path

from attachment_host.base import AttachmentHost

_instance: AttachmentHost | None = None


def get_host() -> AttachmentHost:
    global _instance
    if _instance is None:
        name = os.environ.get("PDLC_ATTACHMENT_HOST", "file")
        if name == "file":
            from attachment_host.file import FileAttachmentHost

            _instance = FileAttachmentHost()
        elif name == "none":
            from attachment_host.none import NoneAttachmentHost

            _instance = NoneAttachmentHost()
        else:
            raise RuntimeError(f"unknown PDLC_ATTACHMENT_HOST: {name!r}")
    return _instance


def reset_host() -> None:
    """Test hook: drop the cached host so the next call re-reads env."""
    global _instance
    _instance = None


def save_for(scope: str, source: str | Path, description: str | None = None) -> dict:
    return get_host().save_for(scope, source, description)


def save_image_for(scope: str, source: str | Path, description: str | None = None) -> dict:
    return get_host().save_image_for(scope, source, description)


def get_for(scope: str, attachment_id: str) -> dict:
    return get_host().get_for(scope, attachment_id)


def get_image_for(scope: str, attachment_id: str) -> Path:
    return get_host().get_image_for(scope, attachment_id)


def list_for(scope: str) -> list[dict]:
    return get_host().list_for(scope)
