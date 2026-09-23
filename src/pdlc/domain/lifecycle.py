"""Pure lifecycle vocabulary and validation primitives."""

from __future__ import annotations


class PdlcError(RuntimeError):
    """A user-facing pdlc failure. Callers catch this at the CLI boundary,
    print str(error) to stderr, and exit 1 — mirroring the shell `die`."""


class NotFound(PdlcError):
    """The requested identity is absent; operational failures use PdlcError."""


MARKERS = [
    "PRODUCT", "UI", "TASKS", "PLAN", "IMPLEMENTATION",
    "TESTING", "REVIEW", "COMPLETE",
    "APPROVED", "AUTOAPPROVED", "INVALIDATED", "SKIPPED", "DECISION", "RESOLUTION",
    "PATCHED",
]


def require_marker(candidate: str | None) -> None:
    valid = " ".join(MARKERS)
    if not candidate:
        raise PdlcError(f"an evidence marker is required; valid markers: {valid}")
    if candidate not in MARKERS:
        raise PdlcError(f"unknown evidence marker: {candidate}; valid markers: {valid}")


def duplicates(values: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [value for value, count in counts.items() if count > 1]
