"""File-backed PDLC attachments.

Each Work Item owns one local attachment directory:

    .pdlc/<work-item-number>/attachments/files.json
    .pdlc/<work-item-number>/attachments/att_<sha256>.<extension>

The metadata file is local-only and contains only the attachment ID, optional
description, and relative path. Reads never create the attachment directory.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
from pathlib import Path

from attachment_host.base import AttachmentHost
from pdlc_common import PdlcError

_MANIFEST_VERSION = 1
_IMAGE_MEDIA_TYPE_PREFIX = "image/"


def _root() -> Path:
    return Path(os.environ.get("PDLC_HOME", ".pdlc"))


def _safe_component(value: str, label: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise PdlcError(f"{label} must be one safe path component: {value!r}")
    return value


def _attachments_dir(scope: str, *, create: bool = False) -> Path:
    safe_scope = _safe_component(str(scope), "attachment scope")
    path = _root() / safe_scope / "attachments"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _manifest_path(directory: Path) -> Path:
    return directory / "files.json"


def _read_manifest(directory: Path) -> dict:
    path = _manifest_path(directory)
    if not path.exists():
        return {"version": _MANIFEST_VERSION, "files": []}
    try:
        manifest = json.loads(path.read_text())
    except (OSError, UnicodeError) as error:
        raise PdlcError(f"attachment metadata could not be read: {path}: {error}") from None
    except json.JSONDecodeError as error:
        raise PdlcError(f"attachment metadata is not valid JSON: {path}: {error}") from None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise PdlcError(f"attachment metadata has an invalid shape: {path}")
    if manifest.get("version", _MANIFEST_VERSION) != _MANIFEST_VERSION:
        raise PdlcError(f"attachment metadata has an unsupported version: {path}")

    identifiers: set[str] = set()
    for index, entry in enumerate(manifest["files"]):
        if not isinstance(entry, dict):
            raise PdlcError(f"attachment metadata entry {index + 1} is not an object: {path}")

        attachment_id = entry.get("id")
        if not isinstance(attachment_id, str) or not attachment_id:
            raise PdlcError(f"attachment metadata entry {index + 1} has an invalid ID: {path}")
        try:
            _safe_component(attachment_id, "attachment ID")
        except PdlcError:
            raise PdlcError(f"attachment metadata entry {index + 1} has an unsafe ID: {path}") from None
        if attachment_id in identifiers:
            raise PdlcError(f"attachment metadata contains duplicate ID {attachment_id!r}: {path}")
        identifiers.add(attachment_id)

        description = entry.get("description")
        if description is not None and not isinstance(description, str):
            raise PdlcError(f"attachment metadata entry {index + 1} has an invalid description: {path}")

        relative_path = entry.get("path")
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or relative_path.startswith(("/", "\\"))
            or "\x00" in relative_path
        ):
            raise PdlcError(f"attachment metadata entry {index + 1} has an invalid path: {path}")
    return manifest


def _write_manifest(directory: Path, manifest: dict) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix="files.", suffix=".tmp", dir=directory)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        temporary_path.replace(_manifest_path(directory))
    finally:
        temporary_path.unlink(missing_ok=True)


def _source_path(source: str | Path) -> Path:
    path = Path(source)
    if not path.is_file():
        raise PdlcError(f"attachment source is not a regular file: {source}")
    return path


def _media_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _resolved_path(directory: Path, metadata: dict) -> Path:
    relative_path = metadata.get("path")
    if not isinstance(relative_path, str) or not relative_path:
        raise PdlcError(f"attachment metadata has no relative path: {metadata.get('id', '<unknown>')}")
    path = (directory / relative_path).resolve()
    root = directory.resolve()
    if path == root or root not in path.parents:
        raise PdlcError(f"attachment path escapes its scope: {relative_path}")
    if not path.is_file():
        raise PdlcError(f"attachment file does not exist: {path}")
    return path


class FileAttachmentHost(AttachmentHost):
    capabilities = {"local_path"}

    def save_for(self, scope: str, source: str | Path, description: str | None = None) -> dict:
        source_path = _source_path(source)
        directory = _attachments_dir(scope, create=True)
        manifest = _read_manifest(directory)
        digest = hashlib.sha256()
        temporary_path: Path | None = None

        try:
            descriptor, temporary_name = tempfile.mkstemp(prefix="attachment.", dir=directory)
            temporary_path = Path(temporary_name)
            with source_path.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
                while chunk := input_handle.read(1024 * 1024):
                    digest.update(chunk)
                    output_handle.write(chunk)

            attachment_id = f"att_{digest.hexdigest()}"
            existing = next((entry for entry in manifest["files"] if entry.get("id") == attachment_id), None)
            if existing:
                if description and description.strip() and existing.get("description") != description.strip():
                    existing["description"] = description.strip()
                    _write_manifest(directory, manifest)
                return self._view(directory, existing)

            payload_name = f"{attachment_id}{source_path.suffix.lower()}"
            payload_path = directory / payload_name
            temporary_path.replace(payload_path)
            temporary_path = None
            entry = {
                "id": attachment_id,
                "description": description.strip() if description and description.strip() else None,
                "path": payload_name,
            }
            manifest["version"] = _MANIFEST_VERSION
            manifest["files"].append(entry)
            _write_manifest(directory, manifest)
            return self._view(directory, entry)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def save_image_for(self, scope: str, source: str | Path, description: str | None = None) -> dict:
        source_path = _source_path(source)
        if not _media_type(source_path).startswith(_IMAGE_MEDIA_TYPE_PREFIX):
            raise PdlcError(f"attachment is not an image: {source}")
        return self.save_for(scope, source_path, description)

    def get_for(self, scope: str, attachment_id: str) -> dict:
        directory = _attachments_dir(scope)
        attachment_id = _safe_component(str(attachment_id), "attachment ID")
        metadata = next((entry for entry in _read_manifest(directory)["files"] if entry.get("id") == attachment_id), None)
        if metadata is None:
            raise PdlcError(f"no attachment {attachment_id!r} for scope {scope!r}")
        return self._view(directory, metadata)

    def get_image_for(self, scope: str, attachment_id: str) -> Path:
        attachment = self.get_for(scope, attachment_id)
        if not _media_type(Path(attachment["path"])).startswith(_IMAGE_MEDIA_TYPE_PREFIX):
            raise PdlcError(f"attachment is not an image: {attachment_id}")
        return Path(attachment["path"])

    def list_for(self, scope: str) -> list[dict]:
        directory = _attachments_dir(scope)
        return [self._view(directory, entry) for entry in _read_manifest(directory)["files"]]

    def _view(self, directory: Path, metadata: dict) -> dict:
        return {
            "id": metadata["id"],
            "description": metadata.get("description"),
            "path": str(_resolved_path(directory, metadata)),
        }
