"""The attachment-host port for local PDLC binary artifacts.

The host returns only the attachment ID, optional description, and path. A
future host may put a URL in that path without changing the PDLC inspectors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class AttachmentHost(ABC):
    """Stores and resolves PDLC attachments for an agent or publisher."""

    capabilities: set[str] = set()

    @abstractmethod
    def save_for(self, scope: str, source: str | Path, description: str | None = None) -> dict:
        """Save one attachment and return its ID, description, and path."""

    @abstractmethod
    def save_image_for(self, scope: str, source: str | Path, description: str | None = None) -> dict:
        """Save one image attachment and reject non-image files."""

    @abstractmethod
    def get_for(self, scope: str, attachment_id: str) -> dict:
        """Resolve one attachment by ID and return its metadata plus path."""

    @abstractmethod
    def get_image_for(self, scope: str, attachment_id: str) -> Path:
        """Resolve one attachment by ID and return its local image path."""

    def list_for(self, scope: str) -> list[dict]:
        """Return all attachments registered for a scope, oldest first."""
