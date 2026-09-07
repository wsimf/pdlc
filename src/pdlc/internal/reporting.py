"""Small Markdown/YAML rendering primitives shared by PDLC inspectors."""

from __future__ import annotations

import json
from typing import Any


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value)


def yaml_lines(value: Any, indent: int = 0) -> list[str]:
    pad = "  " * indent

    if isinstance(value, dict):
        lines = []
        for key, child in value.items():
            if isinstance(child, (dict, list)) and child:
                lines.append(f"{pad}{key}:")
                lines.extend(yaml_lines(child, indent + 1))
            elif isinstance(child, dict):
                lines.append(f"{pad}{key}: {{}}")
            elif isinstance(child, list):
                lines.append(f"{pad}{key}: []")
            else:
                lines.append(f"{pad}{key}: {yaml_scalar(child)}")
        return lines

    if isinstance(value, list):
        lines = []
        for child in value:
            if isinstance(child, dict):
                child_lines = yaml_lines(child, indent + 1)
                lines.append(f"{pad}- {child_lines[0].strip()}")
                lines.extend(child_lines[1:])
            else:
                lines.append(f"{pad}- {yaml_scalar(child)}")
        return lines

    return [f"{pad}{yaml_scalar(value)}"]


def yaml_front_matter(data: dict) -> str:
    return "---\n" + "\n".join(yaml_lines(data)) + "\n---"


def older_comments_notice(target: str | int, metadata: dict | None, loaded: int) -> str:
    """Render guidance when the backend returned only its bounded comment window."""
    total = int((metadata or {}).get("totalCount", loaded))
    older = total - loaded
    if older <= 0:
        return ""
    return f"{older} more comments; use pdlc inspect comments {target} --page 2"
