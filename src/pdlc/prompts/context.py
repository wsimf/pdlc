"""Turn record reads into the values the sibling ``docs/`` fragments interpolate.

The fragments own the wording; this module only resolves what each placeholder
stands for, so a prompt's text is changed in ``docs/`` and the sourcing of its
values is changed here. Everything is derived from data already read off the
record — nothing is inferred from branch names, file layout, or prose.
"""

from __future__ import annotations

import re

from pdlc.domain.model import (
    IMPLEMENTATION_COMMENT_HEADING,
    PLAN_COMMENT_HEADING,
    evidence_comment_text,
    read_section,
)
from pdlc.domain.task_plan import REQUIREMENT_ID_PATTERN, REQUIREMENT_NUMBER

FR_C_PATTERN = REQUIREMENT_ID_PATTERN
UJ_PATTERN = re.compile(r"\bUJ-[0-9]+\b")
_TASK_TAG = re.compile(r"\bWORK-[0-9]+-TASK-[0-9]+\b")
_HEADING = re.compile(rf"^#{{1,6}}\s*(?P<id>[A-Z]+-{REQUIREMENT_NUMBER})\b")


def identifier_blocks(text: str) -> dict[str, str]:
    """Every ``### FR-1: ...`` style block in ``text``, full text, keyed by id.

    Generalises the journey reader: a requirement, constraint, or journey is
    written as its own heading, and its block runs to the next heading.
    """
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        match = _HEADING.match(raw_line.strip())
        if match:
            current = match.group("id")
            blocks[current] = [raw_line.rstrip()]
            continue
        if current:
            blocks[current].append(raw_line.rstrip())
    return {key: "\n".join(lines).strip() for key, lines in blocks.items()}


def covered_text(parent_body: str, section: str, task_body: str, pattern: re.Pattern[str]) -> str:
    """The full text of every identifier ``task_body`` cites, from one parent section.

    An id written as its own heading contributes its whole block; one that only
    appears inline contributes the lines naming it, so a record that lists
    requirements as bullets still resolves. Unresolvable ids are named rather
    than dropped, so a prompt never silently omits a requirement.
    """
    cited = sorted(set(pattern.findall(task_body or "")))
    if not cited:
        return "none"
    source = read_section(parent_body or "", section)
    blocks = identifier_blocks(source)
    rendered: list[str] = []
    for identifier in cited:
        block = blocks.get(identifier)
        if block is None:
            inline = [line.strip() for line in source.splitlines() if identifier in pattern.findall(line)]
            block = "\n".join(inline) if inline else f"{identifier} — not found in the record's `## {section}`"
        rendered.append(block)
    return "\n\n".join(rendered)


def task_tag(task: dict) -> str:
    """The ``WORK-N-TASK-NNN`` tag, read off the task's own title."""
    match = _TASK_TAG.search(task.get("title") or "")
    return match.group(0) if match else (task.get("taskId") or f"#{task['number']}")


def task_headline(task: dict) -> str:
    """The task's title with its ``WORK-N-TASK-NNN`` tag removed."""
    title = (task.get("title") or "").strip()
    return _TASK_TAG.sub("", title).strip() or title


def plan_body(task: dict) -> str:
    """The task's technical plan without its heading; the fragment supplies one."""
    plan = (task.get("planComment") or "").strip()
    if not plan:
        return "none recorded"
    return _strip_heading(plan, PLAN_COMMENT_HEADING)


def implementation_summary(task: dict) -> str:
    """What a task shipped, from its own ``## Implementation`` evidence comment."""
    for comment in task.get("commentObjects") or []:
        body = (comment.get("body") or "").strip()
        if body.startswith(IMPLEMENTATION_COMMENT_HEADING):
            return _strip_heading(evidence_comment_text(comment).strip(), IMPLEMENTATION_COMMENT_HEADING)
    return ""


def dependency_summaries(upstream: list[dict]) -> str:
    """One line per already-implemented upstream task, naming what it shipped."""
    lines: list[str] = []
    for task in upstream:
        summary = implementation_summary(task)
        first = summary.splitlines()[0].strip() if summary else "implemented; no recorded summary"
        lines.append(f"- `{task_tag(task)}` {task_headline(task)}: {first}")
    return "\n".join(lines) if lines else "none"


def _strip_heading(text: str, heading: str) -> str:
    """Drop a leading evidence heading line, keeping the body under it."""
    lines = text.splitlines()
    if lines and lines[0].strip() == heading.strip():
        return "\n".join(lines[1:]).strip()
    return text.strip()
