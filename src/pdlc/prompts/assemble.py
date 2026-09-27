"""Assemble agent prompts from the Markdown fragments bundled in the sibling ``docs/``.

The fragments are the contract; this module is only the substitution engine that
joins them. See ``docs/prompt-template-engine.md`` for the full reference; this
docstring is the short version.

It understands these template forms:

``{{NAME}}``
    Replaced by ``context["NAME"]``. Substituted wherever it appears, including
    mid-line, so a fragment can interpolate a value into running prose.

``{{INCLUDE:path}}``
    Replaced by the fragment at ``path``, relative to ``docs/``, rendered against
    the same context so an included fragment may itself use any directive. The
    fragment's trailing newlines are dropped and the including line's own newline
    is kept, so an include on its own line contributes exactly its own lines.

``{{#IF NAME}} ... {{#ELSE}} ... {{/IF}}``
    Kept when ``context["NAME"]`` is truthy (plain Python truthiness); the
    optional ``{{#ELSE}}`` body — everything from ``{{#ELSE}}`` to the matching
    ``{{/IF}}`` — is kept when it is falsy. ``{{#ELSE}}`` sits alone on its line
    at the ``{{#IF}}``'s own nesting level; at most one per ``{{#IF}}``, and it
    is invalid inside ``{{#EACH}}`` or outside any block.

``{{#EACH NAME}} ... {{/EACH}}``
    The body is rendered once per item in ``context["NAME"]``, which must be a
    sequence of mappings. Inside the body a name resolves against the item first
    and the surrounding context second, so a repeated fragment can still reach
    values that belong to the whole prompt.

Block directives must sit alone on their line; the directive lines themselves are
consumed. Every name a template references must be present in the context, so a
typo fails loudly rather than rendering a prompt with a hole in it. ``check_syntax``
validates a template's structure — balanced blocks, ``#ELSE`` placement, safe and
existing ``INCLUDE`` targets, no unrecognized ``{{...}}`` directive — without a context.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
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
_ELSE = re.compile(r"^[ \t]*\{\{#ELSE\}\}[ \t]*$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\.md$")

# Used only to spot {{...}}-looking text that isn't a real placeholder: an
# unanchored block/#ELSE directive that failed to stand alone on its line, or
# anything else that looks like a directive but matches no known form.
_ANY_DIRECTIVE = re.compile(r"\{\{.*?\}\}")
_BLOCK_OPEN_ANY = re.compile(r"\{\{#(?:IF|EACH)\s+[A-Z0-9_]+\}\}")
_BLOCK_CLOSE_ANY = re.compile(r"\{\{/(?:IF|EACH)\}\}")
_ELSE_ANY = re.compile(r"\{\{#ELSE\}\}")


def package_loader(path: str) -> str:
    """Read a fragment from the installed ``pdlc.prompts.docs`` package data."""
    if not _SAFE_PATH.match(path):
        raise PromptError(f"unsafe fragment path: {path}")
    resource = files("pdlc.prompts").joinpath("docs", *path.split("/"))
    try:
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError) as error:
        raise PromptError(f"no such fragment: {path}") from error


# --- Parsing: turn template lines into a tree of text lines and IF/EACH blocks. ---
# Rendering and `check_syntax` both walk this tree, so the block/ELSE grammar is
# defined once here rather than twice.


@dataclass
class _Text:
    line: str


@dataclass
class _If:
    name: str
    body: list["_Node"]
    else_body: list["_Node"] | None


@dataclass
class _Each:
    name: str
    body: list["_Node"]


_Node = _Text | _If | _Each


def _parse(lines: Sequence[str], index: int) -> tuple[list[_Node], int]:
    """Parse ``lines[index:]`` into nodes, stopping before a close or ``#ELSE`` at this level."""
    nodes: list[_Node] = []
    while index < len(lines):
        directive = lines[index].rstrip("\r\n")
        if _BLOCK_CLOSE.match(directive) or _ELSE.match(directive):
            return nodes, index
        opened = _BLOCK_OPEN.match(directive)
        if opened is None:
            _check_inline(directive)
            nodes.append(_Text(lines[index]))
            index += 1
            continue
        kind, name = opened.group("kind"), opened.group("name")
        body, index = _parse(lines, index + 1)
        else_body: list[_Node] | None = None
        if index < len(lines) and _ELSE.match(lines[index].rstrip("\r\n")):
            if kind != "IF":
                raise PromptError("{{#ELSE}} is only valid inside {{#IF NAME}}")
            else_body, index = _parse(lines, index + 1)
            if index < len(lines) and _ELSE.match(lines[index].rstrip("\r\n")):
                raise PromptError(f"multiple {{{{#ELSE}}}} branches in {{{{#IF {name}}}}}")
        if index >= len(lines):
            raise PromptError(f"unclosed {{{{#{kind} {name}}}}}")
        closed = _BLOCK_CLOSE.match(lines[index].rstrip("\r\n"))
        assert closed is not None  # the loop only stops here on a close, once #ELSE is consumed above
        if closed.group("kind") != kind:
            raise PromptError(f"{{{{#{kind} {name}}}}} closed by {{{{/{closed.group('kind')}}}}}")
        index += 1
        nodes.append(_If(name, body, else_body) if kind == "IF" else _Each(name, body))
    return nodes, index


def _parse_document(text: str) -> list[_Node]:
    """Parse a whole template, rejecting any close or ``#ELSE`` left unmatched at top level."""
    lines = text.splitlines(keepends=True)
    nodes, index = _parse(lines, 0)
    if index < len(lines):
        raise PromptError(f"unexpected {lines[index].rstrip(chr(10)+chr(13)).strip()}")
    return nodes


def _check_inline(line: str) -> None:
    """Reject {{...}}-looking text on a line that isn't a valid inline placeholder."""
    for match in _ANY_DIRECTIVE.finditer(line):
        token = match.group()
        if _PLACEHOLDER.fullmatch(token):
            continue
        if token == "{{/ELSE}}":
            raise PromptError("{{/ELSE}} is no longer valid; an {{#ELSE}} body now runs until {{/IF}}")
        if _BLOCK_OPEN_ANY.fullmatch(token) or _BLOCK_CLOSE_ANY.fullmatch(token) or _ELSE_ANY.fullmatch(token):
            raise PromptError(f"block directive must be alone on its line: {token}")
        raise PromptError(f"unknown directive: {token}")


def check_syntax(text: str, *, path_exists: Callable[[str], bool] | None = None) -> None:
    """Validate a template's syntax without a context.

    Checks balanced ``{{#IF}}``/``{{#EACH}}`` blocks, ``{{#ELSE}}`` placement, that
    every ``{{INCLUDE:path}}`` is a safe path (and exists, when ``path_exists`` is
    given), and that no other ``{{...}}``-looking text is present. Raises
    ``PromptError`` on the first problem found.
    """
    nodes = _parse_document(text)
    _check_includes(nodes, path_exists)


def _check_includes(nodes: Sequence[_Node], path_exists: Callable[[str], bool] | None) -> None:
    for node in nodes:
        if isinstance(node, _Text):
            for match in _PLACEHOLDER.finditer(node.line):
                path = match.group("path")
                if path is None:
                    continue
                if not _SAFE_PATH.match(path):
                    raise PromptError(f"unsafe fragment path: {path}")
                if path_exists is not None and not path_exists(path):
                    raise PromptError(f"no such fragment: {path}")
        elif isinstance(node, _If):
            _check_includes(node.body, path_exists)
            if node.else_body is not None:
                _check_includes(node.else_body, path_exists)
        else:
            _check_includes(node.body, path_exists)


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
    return _render_nodes(_parse_document(template), context, loader, _stack)


def _render_nodes(
    nodes: Sequence[_Node],
    context: PromptContext,
    loader: FragmentLoader,
    stack: tuple[str, ...],
) -> str:
    """Render a parsed node tree, evaluating each block against ``context``."""
    out: list[str] = []
    for node in nodes:
        if isinstance(node, _Text):
            out.append(_render_line(node.line, context, loader, stack))
        elif isinstance(node, _If):
            selected = node.body if _lookup(node.name, context) else node.else_body
            if selected is not None:
                out.append(_render_nodes(selected, context, loader, stack))
        else:
            value = _lookup(node.name, context)
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                raise PromptError(
                    f"{{{{#EACH {node.name}}}}} needs a sequence of mappings, got {type(value).__name__}"
                )
            for item in value:
                if not isinstance(item, Mapping):
                    raise PromptError(
                        f"{{{{#EACH {node.name}}}}} items must be mappings, got {type(item).__name__}"
                    )
                out.append(_render_nodes(node.body, _ChainedContext(item, context), loader, stack))
    return "".join(out)


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
