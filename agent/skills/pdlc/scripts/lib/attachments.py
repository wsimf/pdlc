"""Shared local attachment parsing, persistence, and rendering helpers."""

from __future__ import annotations

import re
from pathlib import Path

from attachment_host import get_host
from pdlc_common import PdlcError, require_file

_TASK_PARENT_PATTERN = re.compile(r"^WORK-(\d+)-TASK-\d{3}")


def parse_attachment_arguments(argv: list[str]) -> tuple[list[str], list[dict]]:
    """Extract repeated `--attachment PATH [--attachment-description TEXT]` pairs."""
    remaining: list[str] = []
    attachments: list[dict] = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--attachment-description":
            raise PdlcError("--attachment-description must immediately follow --attachment")
        if argument != "--attachment":
            remaining.append(argument)
            index += 1
            continue
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            raise PdlcError("--attachment requires a file path")
        path = argv[index + 1]
        description = None
        index += 2
        if index < len(argv) and argv[index] == "--attachment-description":
            if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
                raise PdlcError("--attachment-description requires text")
            description = argv[index + 1]
            index += 2
        attachments.append({"path": path, "description": description})
    return remaining, attachments


def save_attachments(scope: str | int, attachments: list[dict]) -> list[dict]:
    """Validate every source before copying any attachment into the scope."""
    validated = validate_attachments(attachments)
    host = get_host()
    return [host.save_for(str(scope), entry["path"], entry["description"]) for entry in validated]


def validate_attachments(attachments: list[dict]) -> list[dict]:
    """Validate all attachment sources without creating local storage."""
    return [
        {"path": require_file("attachment", entry.get("path")), "description": entry.get("description")}
        for entry in attachments
    ]


def attachments_for_item(item: dict) -> list[dict]:
    return get_host().list_for(work_item_number(item))


def work_item_number(item: dict) -> str:
    number = item.get("number") or (item.get("content") or {}).get("number")
    if number is None:
        raise PdlcError("work item has no number for attachment lookup")
    return str(number)


def parent_number_for_task(task: dict) -> str:
    match = _TASK_PARENT_PATTERN.match(task.get("title") or "")
    if not match:
        raise PdlcError(f"delivery task has no stable parent identity: {task.get('title') or '<untitled>'}")
    return match.group(1)


def attachments_markdown(attachments: list[dict]) -> str:
    if not attachments:
        return "## Attachments\n\nNone"
    lines = ["## Attachments"]
    for index, attachment in enumerate(attachments, start=1):
        description = (attachment.get("description") or "").strip() or Path(attachment["path"]).name
        lines.extend(["", f"{index}. {description}", attachment["path"]])
    return "\n".join(lines)
