"""Load the bundled evidence templates and check a body against one.

A template in the sibling ``docs/`` is both the outline an agent fills in and
the schema a body is checked against: every line starting with ``### `` names
a section the body must carry with real content, unless the heading ends with
``<!-- optional -->``. The validator reads the sections from the template text
rather than hardcoding them, so a template can change (or, later, be
overridden per repository) without touching the commands that enforce it.

Commands call ``require_template`` before any side effect; its error lists
every problem and then prints the template, so an agent can rewrite the body
from the error alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import re

from pdlc.domain.lifecycle import PdlcError

_NAME_CHARACTERS = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_COMMENT_RE = re.compile(r"<!--(.*?)-->")
_SCHEMA_HEADING_RE = re.compile(r"^###\s+(.+?)\s*$")
_BODY_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_THEMATIC_BREAK_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")
# A bullet left exactly as the template's `- <placeholder>` was never filled in.
_PLACEHOLDER_RE = re.compile(r"^[-*]\s+<[^>]*>$")


@dataclass(frozen=True)
class Section:
    name: str
    optional: bool


def template_names() -> list[str]:
    """Every bundled template, by the name `pdlc template NAME` accepts."""
    return sorted(
        resource.name.removesuffix(".md")
        for resource in files("pdlc.templates").joinpath("docs").iterdir()
        if resource.name.endswith(".md")
    )


def load_template(name: str) -> str:
    """Return the template's Markdown, raising `PdlcError` for an unknown name."""
    if not _NAME_CHARACTERS.match(name) or name not in template_names():
        raise PdlcError(f"no template named {name!r}; available: {', '.join(template_names())}")
    return files("pdlc.templates").joinpath("docs", f"{name}.md").read_text(encoding="utf-8")


def template_sections(template: str) -> list[Section]:
    """The sections a template declares, in template order."""
    sections = []
    for line in template.splitlines():
        heading = _SCHEMA_HEADING_RE.match(line.strip())
        if heading:
            text = heading.group(1)
            optional = any("optional" in comment.lower() for comment in _COMMENT_RE.findall(text))
            sections.append(Section(_COMMENT_RE.sub("", text).strip(), optional))
    return sections


def _body_sections(body: str) -> dict[str, list[str]]:
    """Content lines under each heading, keyed by lowercased heading text. A
    thematic break (`---`) ends the current section, so a footer below it
    never counts as a section's content."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for raw in body.splitlines():
        line = raw.strip()
        heading = _BODY_HEADING_RE.match(line)
        if heading:
            current = found.setdefault(_COMMENT_RE.sub("", heading.group(1)).strip().lower(), [])
            continue
        if _THEMATIC_BREAK_RE.match(line):
            current = None
            continue
        if current is not None and line:
            current.append(line)
    return found


def template_problems(template: str, body: str) -> list[str]:
    """Every way `body` falls short of `template`, in template order; empty
    when it conforms. Headings the template does not declare are allowed."""
    found = _body_sections(body)
    problems = []
    for section in template_sections(template):
        lines = found.get(section.name.lower())
        if lines is None:
            if not section.optional:
                problems.append(f"missing section: ### {section.name}")
            continue
        content = [line for line in lines if not _PLACEHOLDER_RE.match(line)]
        if not content:
            problems.append(f"no content under: ### {section.name}" + (" (fill it in or drop the heading)" if section.optional else ""))
        elif len(content) < len(lines):
            problems.append(f"unfilled placeholder under: ### {section.name}")
    return problems


def require_template(name: str, body: str, label: str) -> None:
    """Raise `PdlcError` naming every problem, followed by the template itself,
    when `body` does not follow the named template."""
    template = load_template(name)
    problems = template_problems(template, body)
    if not problems:
        return
    listed = "\n".join(f"- {problem}" for problem in problems)
    raise PdlcError(
        f"the {label} does not follow the {name} template:\n{listed}\n\n"
        f"Rewrite it to this template (`pdlc template {name}` prints it again):\n\n{template.rstrip()}"
    )
