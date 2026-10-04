"""GitHub CLI transport, repository coordinates, and safe body files."""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Literal, Sequence

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.lib.process import parse_json, run_process
from pdlc.config import get_config


# How a `gh` call affects the host, which decides whether a transient failure
# may be retried and whether it leaves the run with a write that may have landed.
# "read" changes nothing; "set" replaces a value outright, so running it twice
# leaves the same result as once; "add" is anything else (`issue create`,
# `issue comment`, `project item-add`, every `stack` write, an unknown call),
# which a retry could duplicate.
CallKind = Literal["read", "set", "add"]

_GH_READS = {
    ("issue", "view"), ("issue", "list"), ("pr", "view"), ("pr", "list"), ("pr", "checks"),
    ("project", "view"), ("project", "list"), ("project", "field-list"), ("project", "item-list"),
    ("stack", "view"), ("extension", "list"), ("auth", "status"), ("repo", "view"),
}
_GH_SETS = {
    ("issue", "edit"), ("issue", "close"), ("issue", "reopen"),
    ("pr", "edit"), ("pr", "ready"), ("project", "item-edit"),
}

# The only GraphQL mutation pdlc sends that sets a value rather than adding one.
_SET_MUTATIONS = {"updateProjectV2ItemFieldValue"}
_MUTATION_FIELD = re.compile(r"(?:\w+\s*:\s*)?(\w+)\s*\(\s*input\s*:")
_BODY_FLAGS = {"-f", "-F", "--field", "--raw-field", "--input"}


def _graphql_kind(args: Sequence[str]) -> CallKind:
    query = next((arg.partition("=")[2] for arg in args if arg.startswith("query=")), "")
    text = query.lstrip()
    if not text.startswith("mutation"):
        return "read"
    fields = set(_MUTATION_FIELD.findall(text))
    return "set" if fields and fields <= _SET_MUTATIONS else "add"


def _rest_method(args: Sequence[str]) -> str:
    for flag in ("--method", "-X"):
        if flag in args:
            index = list(args).index(flag)
            if index + 1 < len(args):
                return args[index + 1].upper()
    # `gh api` switches to POST as soon as it is given a body field.
    return "POST" if any(arg in _BODY_FLAGS for arg in args) else "GET"


def gh_call_kind(args: Sequence[str]) -> CallKind:
    if not args:
        return "add"
    if args[0] == "api":
        if len(args) > 1 and args[1] == "graphql":
            return _graphql_kind(args)
        method = _rest_method(args)
        # A retried DELETE sees 404, which `delete_comment` treats as done.
        return "read" if method == "GET" else "set" if method in {"PATCH", "PUT", "DELETE"} else "add"
    pair = tuple(args[:2])
    return "read" if pair in _GH_READS else "set" if pair in _GH_SETS else "add"


def run_gh(args: Sequence[str], *, input: str | None = None, timeout: float = 120) -> str:
    kind = gh_call_kind(args)
    return run_process(
        ["gh", *args], input=input, timeout=timeout, idempotent=kind != "add", writes=kind != "read",
        # A stack write pushes and edits several branches and PRs in one call.
        single_request=not (args and args[0] == "stack"),
    )


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


# Issues and the Project live in the tracker repository; pull requests live in
# the code repository. The two differ when several code repositories share one
# tracker, so every `gh` call names the side it reads or writes.


def tracker_repo_args() -> list[str]:
    """`--repo` for an Issue call: `[tracker.github] repository`."""
    repository = get_config().tracker_repository
    return ["--repo", repository] if repository else []


def code_repo_args(repository: str = "") -> list[str]:
    """`--repo` for a pull-request call: `repository` (a `PullRef`'s), else
    `[code.github] repository`."""
    repository = repository or get_config().code_repository or ""
    return ["--repo", repository] if repository else []


def assignee_args() -> list[str]:
    """`gh issue create` flags assigning a new Issue to the configured
    `[tracker.github] assigned_to` login, or to the authenticated user when
    that is unset — `gh` resolves `@me` itself, so neither costs a lookup."""
    configured = (get_config().github_assigned_to or "").strip()
    return ["--assignee", configured if configured and configured.casefold() != "@me" else "@me"]


def _owner_name(repository: str | None, table: str) -> tuple[str, str]:
    if not repository or "/" not in repository:
        raise PdlcError(f"[{table}] repository must be owner/name")
    owner, _, name = repository.partition("/")
    return owner, name


def tracker_owner_repository() -> tuple[str, str]:
    """`(owner, name)` of the tracker repository, for Issue GraphQL reads."""
    return _owner_name(get_config().tracker_repository, "tracker.github")


def code_owner_repository(repository: str = "") -> tuple[str, str]:
    """`(owner, name)` of `repository` (a `PullRef`'s), else of the code
    repository, for pull-request GraphQL reads."""
    return _owner_name(repository or get_config().code_repository, "code.github")


# A bare `#123` that GitHub would autolink to an issue/PR and record as a
# cross-reference. Excludes anything already escaped (`\#`), an HTML entity
# (`&#123;`), a `##` run, and a qualified `repo#123` (preceded by a name
# character). A digit run followed by more word characters (`#123abc`) is not a
# reference and is left alone.
_LOOSE_ISSUE_REF = re.compile(r"(?<![\w#&\\])#(\d+)\b")
# The escaped form `neutralize_refs` writes, under the same lookbehind.
_ESCAPED_ISSUE_REF = re.compile(r"(?<![\w#&\\])\\#(\d+)\b")


def neutralize_refs(text: str) -> str:
    """Defuses loose `#123` issue/PR references in agent-authored body text so
    GitHub renders them verbatim without autolinking or firing a
    cross-reference event, by backslash-escaping the hash (`#123` -> `\\#123`).

    Deliberate references are unaffected: full github.com URLs, `owner/repo#123`,
    and closing keywords (`Closes #123`) are all left intact. Runs line by line
    and skips fenced code blocks; a `#123` inside an inline code span is escaped
    too, which is harmless (it renders in a code span either way).
    """
    return _outside_fences(text, lambda line: _LOOSE_ISSUE_REF.sub(r"\\#\1", line))


def restore_refs(text: str) -> str:
    """The inverse of `neutralize_refs`, applied to every body and comment read
    back, so callers above the host port see the text they wrote. Escaping is a
    GitHub rendering concern and never leaves this backend.

    `neutralize_refs(restore_refs(stored)) == stored` for anything this backend
    wrote. The reverse is lossy only for text that already carried a loose `\\#123`
    of its own, which reads back as `#123`.
    """
    return _outside_fences(text, lambda line: _ESCAPED_ISSUE_REF.sub(r"#\1", line))


def _outside_fences(text: str, rewrite: Callable[[str], str]) -> str:
    out: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(line)
            continue
        out.append(line if in_fence else rewrite(line))
    return "".join(out)


@contextmanager
def body_file(text: str) -> Iterator[str]:
    """Writes `text` — with loose GitHub references neutralized — to a cached
    `.md` file for `gh ... --body-file`, yields its path, and removes it after.
    Every GitHub-backend write of agent-authored body or comment content goes
    through here so the neutralization has a single chokepoint.
    """
    # Request payloads can be created before a record exists, so they use the
    # unscoped cache directory and are removed as soon as `gh` finishes.
    from pdlc.internal.scratch import scratch_path, write_scratch

    path = write_scratch(scratch_path("unscoped", "github-body"), neutralize_refs(text))
    try:
        yield str(path)
    finally:
        path.unlink(missing_ok=True)
