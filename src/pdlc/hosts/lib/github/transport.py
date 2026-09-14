"""GitHub CLI transport, repository coordinates, and safe body files."""

from __future__ import annotations

import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.lib.process import parse_json, run_process
from pdlc.config import get_config


def run_gh(args: Sequence[str], *, input: str | None = None) -> str:
    return run_process(["gh", *args], input=input)


def run_gh_json(args: Sequence[str], **kwargs: Any) -> Any:
    return parse_json(run_gh(args, **kwargs), "gh")


def run_graphql(query: str, **variables: Any) -> dict:
    """Runs `gh api graphql` with one query and its variables, typing each
    variable as GraphQL Int (-F) or String/ID (-f) from its Python type."""
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        flag = "-F" if isinstance(value, int) and not isinstance(value, bool) else "-f"
        args += [flag, f"{key}={value}"]
    return run_gh_json(args)


def repo_args() -> list[str]:
    repository = get_config().repository
    return ["--repo", repository] if repository else []


def assignee_args() -> list[str]:
    """`gh issue create` flags assigning a new Issue to the configured
    `[backend.github] assigned_to` login, or to the authenticated user when
    that is unset — `gh` resolves `@me` itself, so neither costs a lookup."""
    configured = (get_config().github_assigned_to or "").strip()
    return ["--assignee", configured if configured and configured.casefold() != "@me" else "@me"]


def owner_repository() -> tuple[str, str]:
    repository = get_config().repository
    if not repository or "/" not in repository:
        raise PdlcError("PDLC_REPOSITORY must be owner/name to resolve an Issue")
    owner, _, name = repository.partition("/")
    return owner, name


# A bare `#123` that GitHub would autolink to an issue/PR and record as a
# cross-reference. Excludes anything already escaped (`\#`), an HTML entity
# (`&#123;`), a `##` run, and a qualified `repo#123` (preceded by a name
# character). A digit run followed by more word characters (`#123abc`) is not a
# reference and is left alone.
_LOOSE_ISSUE_REF = re.compile(r"(?<![\w#&\\])#(\d+)\b")


def neutralize_refs(text: str) -> str:
    """Defuses loose `#123` issue/PR references in agent-authored body text so
    GitHub renders them verbatim without autolinking or firing a
    cross-reference event, by backslash-escaping the hash (`#123` -> `\\#123`).

    Deliberate references are unaffected: full github.com URLs, `owner/repo#123`,
    and closing keywords (`Closes #123`) are all left intact. Runs line by line
    and skips fenced code blocks; a `#123` inside an inline code span is escaped
    too, which is harmless (it renders in a code span either way).
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(line)
            continue
        out.append(line if in_fence else _LOOSE_ISSUE_REF.sub(r"\\#\1", line))
    return "".join(out)


@contextmanager
def body_file(text: str) -> Iterator[str]:
    """Writes `text` — with loose GitHub references neutralized — to a temporary
    `.md` file for `gh ... --body-file`, yields its path, and removes it after.
    Every GitHub-backend write of agent-authored body or comment content goes
    through here so the neutralization has a single chokepoint.
    """
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md", encoding="utf-8") as handle:
        handle.write(neutralize_refs(text))
        path = handle.name
    try:
        yield path
    finally:
        Path(path).unlink(missing_ok=True)
