"""Selects the PDLC attachment host."""

from __future__ import annotations

from pathlib import Path

from pdlc.config import get_config
from pdlc.hosts.attachment_host.base import AttachmentHost

_instance: AttachmentHost | None = None


def get_host() -> AttachmentHost:
    global _instance
    if _instance is None:
        name = get_config().attachments_provider or "file"
        if name == "file":
            from pdlc.hosts.file_provider import FileAttachmentHost

            _instance = FileAttachmentHost()
        elif name == "none":
            from pdlc.hosts.none_provider import NoneAttachmentHost

            _instance = NoneAttachmentHost()
        else:
            raise RuntimeError(f"unknown [attachments] provider: {name!r}")
    return _instance


def reset_host() -> None:
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
