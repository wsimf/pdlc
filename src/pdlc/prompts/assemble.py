"""Assemble agent prompts from the Markdown fragments bundled in the sibling ``docs/``.

The fragments are the contract; this module is only the substitution engine that
joins them. It understands these template forms:

``{{NAME}}``
    Replaced by ``context["NAME"]``. Substituted wherever it appears, including
    mid-line, so a fragment can interpolate a value into running prose.

``{{INCLUDE:path}}``
    Replaced by the fragment at ``path``, relative to ``docs/``, rendered against
    the same context so an included fragment may itself use any directive. The
    fragment's trailing newlines are dropped and the including line's own newline
    is kept, so an include on its own line contributes exactly its own lines.

``{{#IF NAME}} ... {{#ELSE}} ... {{/ELSE}} ... {{/IF}}``
    Kept when ``context["NAME"]`` is truthy under JavaScript/TypeScript rules; the
    optional ``#ELSE`` body is kept when it is falsy. Empty lists and mappings are
    truthy. Both ELSE directives must sit inside an IF block.

``{{#EACH NAME}} ... {{/EACH}}``
    The body is rendered once per item in ``context["NAME"]``, which must be a
    sequence of mappings. Inside the body a name resolves against the item first
    and the surrounding context second, so a repeated fragment can still reach
    values that belong to the whole prompt.

Block directives must sit alone on their line; the directive lines themselves are
consumed. Every name a template references must be present in the context, so a
typo fails loudly rather than rendering a prompt with a hole in it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib.resources import files
import math
import re
from typing import Protocol

# A context value is either substituted as text, tested for truthiness by
# ``#IF``, or iterated by ``#EACH``; the loader resolves ``INCLUDE`` paths.
PromptContext = Mapping[str, object]


class FragmentLoader(Protocol):
    """Resolves a docs-relative fragment path to its Markdown source."""

    def __call__(self, path: str) -> str: ...


class PromptError(Exception):
    """A template referenced a missing name, fragment, or malformed block."""


_PLACEHOLDER = re.compile(r"\{\{(?:INCLUDE:(?P<path>[A-Za-z0-9_./-]+)|(?P<name>[A-Z0-9_]+))\}\}")
_BLOCK_OPEN = re.compile(r"^[ \t]*\{\{#(?P<kind>IF|EACH)\s+(?P<name>[A-Z0-9_]+)\}\}[ \t]*$")
_BLOCK_CLOSE = re.compile(r"^[ \t]*\{\{/(?P<kind>IF|EACH)\}\}[ \t]*$")
_ELSE_OPEN = re.compile(r"^[ \t]*\{\{#ELSE\}\}[ \t]*$")
_ELSE_CLOSE = re.compile(r"^[ \t]*\{\{/ELSE\}\}[ \t]*$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\.md$")


def package_loader(path: str) -> str:
    """Read a fragment from the installed ``pdlc.prompts.docs`` package data."""
    if not _SAFE_PATH.match(path):
        raise PromptError(f"unsafe fragment path: {path}")
    resource = files("pdlc.prompts").joinpath("docs", *path.split("/"))
    try:
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError) as error:
        raise PromptError(f"no such fragment: {path}") from error


def render(name: str, context: PromptContext, *, loader: FragmentLoader = package_loader) -> str:
    """Assemble the prompt named by ``name`` (e.g. ``implement``) into one string."""
    return render_text(loader(f"{name}.md"), context, loader=loader, _stack=(f"{name}.md",))


def render_text(
    template: str,
    context: PromptContext,
    *,
    loader: FragmentLoader = package_loader,
    _stack: tuple[str, ...] = (),
) -> str:
    """Render raw template source; ``render`` is the entry point callers want."""
    return _render_lines(template.splitlines(keepends=True), context, loader, _stack)


def _render_lines(
    lines: Sequence[str],
    context: PromptContext,
    loader: FragmentLoader,
    stack: tuple[str, ...],
) -> str:
    """Render a run of lines, resolving each block directive against ``context``."""
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        directive = line.rstrip("\r\n")
        if (
            _BLOCK_CLOSE.match(directive)
            or _ELSE_OPEN.match(directive)
            or _ELSE_CLOSE.match(directive)
        ):
            raise PromptError(f"unexpected {directive.strip()}")
        opened = _BLOCK_OPEN.match(directive)
        if opened is None:
            out.append(_render_line(line, context, loader, stack))
            index += 1
            continue
        kind, name = opened.group("kind"), opened.group("name")
        close, alternate = _find_close(lines, index + 1, kind, name)
        body_end = alternate[0] if alternate is not None else close
        alternate_body = lines[alternate[0] + 1 : alternate[1]] if alternate is not None else None
        # The body stays unrendered until the block knows its scope: an #EACH
        # body must be rendered once per item, against that item.
        out.append(
            _render_block(
                kind, name, lines[index + 1 : body_end], alternate_body, context, loader, stack
            )
        )
        index = close + 1
    return "".join(out)


def _find_close(
    lines: Sequence[str], start: int, kind: str, name: str,
) -> tuple[int, tuple[int, int] | None]:
    """Find the block close and, for IF, the ELSE markers at this nesting level."""
    depth = 1
    else_open: int | None = None
    else_close: int | None = None
    for index in range(start, len(lines)):
        directive = lines[index].rstrip("\r\n")
        if _BLOCK_OPEN.match(directive):
            depth += 1
            continue
        closed = _BLOCK_CLOSE.match(directive)
        if closed is not None:
            depth -= 1
            if depth:
                continue
            if closed.group("kind") != kind:
                raise PromptError(f"{{{{#{kind} {name}}}}} closed by {{{{/{closed.group('kind')}}}}}")
            if else_open is not None and else_close is None:
                raise PromptError(f"unclosed {{{{#ELSE}}}} in {{{{#IF {name}}}}}")
            alternate = (else_open, else_close) if else_open is not None and else_close is not None else None
            return index, alternate
        if depth != 1:
            continue
        if _ELSE_OPEN.match(directive):
            if kind != "IF":
                raise PromptError("{{#ELSE}} is only valid inside {{#IF NAME}}")
            if else_open is not None:
                raise PromptError(f"multiple {{{{#ELSE}}}} branches in {{{{#IF {name}}}}}")
            else_open = index
            continue
        if _ELSE_CLOSE.match(directive):
            if else_open is None or else_close is not None:
                raise PromptError("unexpected {{/ELSE}}")
            else_close = index
            continue
    raise PromptError(f"unclosed {{{{#{kind} {name}}}}}")


def _render_block(
    kind: str,
    name: str,
    body: Sequence[str],
    alternate_body: Sequence[str] | None,
    context: PromptContext,
    loader: FragmentLoader,
    stack: tuple[str, ...],
) -> str:
    """Render the selected IF branch or each item in an EACH block."""
    value = _lookup(name, context)
    if kind == "IF":
        selected = body if _is_truthy(value) else alternate_body
        return _render_lines(selected, context, loader, stack) if selected is not None else ""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PromptError(
            f"{{{{#EACH {name}}}}} needs a sequence of mappings, got {type(value).__name__}"
        )
    parts: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise PromptError(
                f"{{{{#EACH {name}}}}} items must be mappings, got {type(item).__name__}"
            )
        parts.append(_render_lines(body, _ChainedContext(item, context), loader, stack))
    return "".join(parts)


def _is_truthy(value: object) -> bool:
    """Apply JavaScript truthiness to prompt values, where empty collections are truthy."""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value)
    if isinstance(value, (int, float)):
        return value != 0 and not (isinstance(value, float) and math.isnan(value))
    return True


def _render_line(
    line: str,
    context: PromptContext,
    loader: FragmentLoader,
    stack: tuple[str, ...],
) -> str:
    """Substitute every placeholder and include occurring within one line."""

    def substitute(match: re.Match[str]) -> str:
        path = match.group("path")
        if path is None:
            return _as_text(match.group("name"), _lookup(match.group("name"), context))
        if path in stack:
            raise PromptError(f"include cycle: {' -> '.join((*stack, path))}")
        # Drop the fragment's trailing newlines; the including line supplies one.
        return render_text(loader(path), context, loader=loader, _stack=(*stack, path)).rstrip("\n")

    return _PLACEHOLDER.sub(substitute, line)


def _lookup(name: str, context: PromptContext) -> object:
    try:
        return context[name]
    except KeyError:
        raise PromptError(f"missing value for {{{{{name}}}}}") from None


def _as_text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise PromptError(f"{{{{{name}}}}} needs a string, got {type(value).__name__}")
    return value


class _ChainedContext(Mapping[str, object]):
    """An ``#EACH`` item's scope, falling back to the surrounding context."""

    def __init__(self, item: Mapping[str, object], parent: PromptContext) -> None:
        self._item = item
        self._parent = parent

    def __getitem__(self, key: str) -> object:
        try:
            return self._item[key]
        except KeyError:
            return self._parent[key]

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter({**self._parent, **self._item})

    def __len__(self) -> int:
        return len({**self._parent, **self._item})
