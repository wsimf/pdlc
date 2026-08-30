"""Null attachment host for environments where binary storage is disabled."""

from __future__ import annotations

from pathlib import Path

from pdlc.attachment_host.base import AttachmentHost
from pdlc.pdlc_common import PdlcError


class NoneAttachmentHost(AttachmentHost):
    def save_for(self, scope: str, source: str | Path, description: str | None = None) -> dict:
        raise PdlcError("no attachment host is configured")

    def save_image_for(self, scope: str, source: str | Path, description: str | None = None) -> dict:
        raise PdlcError("no attachment host is configured")

    def get_for(self, scope: str, attachment_id: str) -> dict:
        raise PdlcError("no attachment host is configured")

    def get_image_for(self, scope: str, attachment_id: str) -> Path:
        raise PdlcError("no attachment host is configured")

    def list_for(self, scope: str) -> list[dict]:
        return []
