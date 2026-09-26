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


def stored_fields(task: dict) -> dict:
    """Rebuild manifest fields from the stored title and task body."""
    body = task.get("body") or ""
    requirements = _field(body, "Requirements Covered")
    journeys = _field(body, "UI Journeys")
    blocked = _field(body, "Blocked by")
    covered_text = " ".join(part for part in (requirements, journeys) if part)
    covers = sorted(set(_COVER.findall(covered_text if requirements is not None else body)))
    title_parts = (task.get("title") or "").split(" ", 2)
    return {
        "title": carried_title(task.get("title") or ""),
        "type": "ui" if "[UI]" in title_parts[:2] else "core",
        "covers": covers,
        "depends": sorted(set(_TASK.findall(blocked))) if blocked is not None else [],
        "body": body,
    }


def snapshot(fields: dict) -> str:
    """Reject a stale generated artifact before it can overwrite a task."""
    payload = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
