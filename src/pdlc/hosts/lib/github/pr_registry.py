"""How the GitHub backend attaches pull requests to an Issue.

GitHub has no field on an Issue for "the pull requests that implement this", so
this backend keeps its own registry in a machine-owned HTML comment pinned to
the top of the Issue body:

    <!-- pdlc:meta
    prs: owner/api#148 owner/web#152
    -->

    ## Scope
    …

Invisible in rendered Markdown, preserved across re-planning, and never shown
to a caller: every body leaving the GitHub backend has the block stripped, and
every body written back has it re-attached. That round trip is this module's
whole responsibility — see `strip`/`restore`.

The block is deliberately minimal. Each `key: value` line's value is
whitespace-split into a token list with no quoting or escaping, which suits the
`owner/name#N` pull-request tokens stored today and is not a general key-value
store. A bare `N` written before pull requests were repository-qualified reads
as the configured code repository's, and is qualified on the next write.
"""

from __future__ import annotations

import re

from pdlc.config import get_config
from pdlc.domain.records import PullRef, parse_pull_refs

_OPEN = "<!-- pdlc:meta"
_PATTERN = re.compile(r"\A<!-- pdlc:meta\n(.*?)\n-->\n?", re.DOTALL)


def read_meta(body: str) -> dict[str, list[str]]:
    match = _PATTERN.match(body or "")
    if not match:
        return {}
    meta: dict[str, list[str]] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, rest = line.partition(":")
            meta[key.strip()] = rest.split()
    return meta


def strip(body: str) -> str:
    """`body` with any metadata block removed — the human-authored content."""
    return _PATTERN.sub("", body or "", count=1).lstrip("\n")


def write_meta(body: str, meta: dict[str, list[str]]) -> str:
    """`body` with its metadata block replaced by `meta` (keys with an empty
    value list are dropped; an empty `meta` removes the block entirely)."""
    clean = strip(body)
    entries = {key: list(values) for key, values in meta.items() if values}
    if not entries:
        return clean
    lines = "\n".join(f"{key}: {' '.join(values)}" for key, values in entries.items())
    return f"{_OPEN}\n{lines}\n-->\n\n{clean}"


def prs(body: str) -> list[PullRef]:
    """The pull requests registered on a raw Issue body, ascending."""
    return parse_pull_refs(read_meta(body).get("prs", []), get_config().pull_request_repository())


def attach(body: str, refs: list[PullRef] | None) -> str:
    """`body` (human content) carrying a registry block for `refs`."""
    return write_meta(body, {"prs": [ref.token() for ref in sorted(set(refs or []))]})


def restore(stored: str, body: str) -> str:
    """`body` (human content) carrying the metadata block found on `stored` (the
    raw Issue body it replaces). Every write path goes through this, so a caller
    that never saw the block cannot drop it."""
    return write_meta(body, read_meta(stored))


def with_pr(stored: str, ref: PullRef) -> tuple[str, list[PullRef]]:
    """The raw body that attaches `ref` to `stored`, and the full list.
    Returns `stored` unchanged when the pull request is already attached.

    The caller's read-modify-write would lose a concurrent body edit made
    between its read and its write. Acceptable while these calls are serialized
    by one agent per record; revisit if bodies become genuinely concurrently
    written."""
    current = prs(stored)
    if ref in current:
        return stored, current
    updated = sorted({*current, ref})
    meta = read_meta(stored)
    meta["prs"] = [entry.token() for entry in updated]
    return write_meta(stored, meta), updated


def view(node: dict) -> dict:
    """A raw Issue/task dict with its body split into human content and `prs`."""
    body = node.get("body") or ""
    return {**node, "body": strip(body), "prs": prs(body)}
