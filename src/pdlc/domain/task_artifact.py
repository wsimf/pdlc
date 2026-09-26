"""Stored delivery tasks as editable planner artifacts."""

from __future__ import annotations

import hashlib
import json
import re

from pdlc.domain.task_plan import carried_title

_COVER = re.compile(r"\b(?:FR|C|UJ)-[0-9]+\b")
_TASK = re.compile(r"\bTASK-[0-9]{3}\b")


def _field(body: str, label: str) -> str | None:
    match = re.search(rf"^\*\*{re.escape(label)}:\*\*\s*(.*)$", body, re.MULTILINE)
    return match.group(1) if match else None


def declared_links(body: str) -> dict[str, list[str]]:
    """The covers and depends a body declares on its labelled lines; an absent label declares nothing."""
    requirements = _field(body, "Requirements Covered")
    blocked = _field(body, "Blocked by")
    links: dict[str, list[str]] = {}
    if requirements is not None:
        journeys = _field(body, "UI Journeys") or ""
        links["covers"] = sorted(set(_COVER.findall(f"{requirements} {journeys}")))
    if blocked is not None:
        links["depends"] = sorted(set(_TASK.findall(blocked)))
    return links


def stored_fields(task: dict) -> dict:
    """Rebuild manifest fields from the stored title and task body."""
    body = task.get("body") or ""
    links = declared_links(body)
    title_parts = (task.get("title") or "").split(" ", 2)
    return {
        "title": carried_title(task.get("title") or ""),
        "type": "ui" if "[UI]" in title_parts[:2] else "core",
        "covers": links.get("covers", sorted(set(_COVER.findall(body)))),
        "depends": links.get("depends", []),
        "body": body,
    }


def snapshot(fields: dict) -> str:
    """Reject a stale generated artifact before it can overwrite a task."""
    payload = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
