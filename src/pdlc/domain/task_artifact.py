"""Stored delivery tasks as editable planner artifacts."""

from __future__ import annotations

import hashlib
import json
import re

from pdlc.domain.task_plan import carried_title

_COVER = re.compile(r"\b(?:FR|C|UJ)-[0-9]+\b")
_TASK = re.compile(r"\bTASK-[0-9]{3}\b")


def _unix_line_endings(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n")


def normalized_task_body(body: str) -> str:
    """Compare task bodies without treating platform line endings or trailing
    whitespace, which a host may add or trim on save, as edits."""
    return _unix_line_endings(body).rstrip()


def same_task_body(left: str, right: str) -> bool:
    return normalized_task_body(left) == normalized_task_body(right)


def same_task_content(left: dict, right: dict) -> bool:
    return left["title"] == right["title"] and left["type"] == right["type"] and same_task_body(left["body"], right["body"])


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


def task_body_errors(body: str, *, is_ui: bool) -> list[str]:
    """Check required planner-body structure; reviewers judge its quality."""
    errors: list[str] = []
    blocked = (_field(body, "Blocked by") or "").strip()
    if not blocked:
        errors.append("add **Blocked by:** None or the TASK-NNN IDs this task depends on")
    elif blocked != "None" and not _TASK.search(blocked):
        errors.append("**Blocked by:** must say None or name at least one TASK-NNN dependency")
    if not (_field(body, "Requirements Covered") or "").strip():
        errors.append("add **Requirements Covered:** with the FR-*/C-* IDs this task delivers")
    if is_ui and not (_field(body, "UI Journeys") or "").strip():
        errors.append("add **UI Journeys:** with the UJ-* IDs this UI task delivers")
    if (_field(body, "Type") or "").strip() not in ("AFK", "HITL"):
        errors.append("add **Type:** AFK or HITL to classify whether implementation needs a human")

    def section(label: str) -> str:
        match = re.search(rf"^\*\*{re.escape(label)}:\*\*\s*\n(.*?)(?=^\*\*[^\n]+:\*\*|\Z)", body, re.MULTILINE | re.DOTALL)
        return match.group(1).strip() if match else ""

    if not section("Scope"):
        errors.append("add a nonempty **Scope:** section describing what this task changes")
    if not any(re.match(r"^- \[ \] \S", line) for line in section("Acceptance Criteria").splitlines()):
        errors.append("add at least one nonempty `- [ ]` item under **Acceptance Criteria:** stating a verifiable outcome")
    return errors


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
    return _hash_fields({**fields, "body": normalized_task_body(fields["body"])})


def baseline_matches(baseline: str, fields: dict) -> bool:
    return baseline == snapshot(fields)


def _hash_fields(fields: dict) -> str:
    payload = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def planner_command(work_item: str, manifest: object) -> str:
    """The brief that starts a planning pass on an existing task manifest."""
    return f"pdlc prompt task-planner {work_item} --current-tasks-manifest-path {manifest} --file"


def reviewer_command(work_item: str, manifest: object) -> str:
    """The brief that hands a task manifest to its reviewer."""
    return f"pdlc prompt tasks-reviewer {work_item} --manifest {manifest} --file"
