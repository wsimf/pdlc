"""The strict, script-owned metadata block at the top of every `PDLC-REVIEW`
comment: stage, verdict, and the rework bounce/loop a Verification run may
carry. The Verification report body under it belongs to
`pdlc.domain.verification`.

Nothing here does I/O: it takes the comment body string and returns plain
data or raises `PdlcError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pdlc.domain.lifecycle import PdlcError

class ReviewVerdict(StrEnum):
    PASS = "Pass"
    CHANGES_REQUIRED = "Changes Required"
    DECISION_REQUIRED = "Decision Required"


@dataclass(frozen=True)
class ReviewEvidence:
    stage: str
    verdict: ReviewVerdict
    bounce: str | None
    loop: str | None


_REVIEW_FIELDS = ("stage", "verdict", "bounce", "loop")


def compose_review(
    stage: str,
    verdict: ReviewVerdict,
    body: str,
    *,
    bounce: str | None = None,
    loop: str | None = None,
) -> str:
    """Compose the script-owned metadata at the top of a PDLC-REVIEW body."""
    if not isinstance(verdict, ReviewVerdict):
        raise TypeError("review verdict must be a ReviewVerdict")
    if not stage.strip():
        raise PdlcError("review stage is empty")
    if (bounce or loop) and verdict != ReviewVerdict.CHANGES_REQUIRED:
        raise PdlcError("review bounce metadata requires verdict Changes Required")
    if bool(bounce) != bool(loop):
        raise PdlcError("review bounce and loop must be supplied together")
    metadata = [
        "---",
        f"stage: {stage.strip()}",
        f"verdict: {verdict.value}",
        f"bounce: {bounce or 'null'}",
        f"loop: {loop or 'null'}",
        "---",
    ]
    payload = body.strip()
    return "\n".join(metadata) + (f"\n\n{payload}\n" if payload else "\n")


def parse_review(body: str) -> ReviewEvidence:
    """Parse the strict YAML-shaped metadata block of a PDLC-REVIEW comment."""
    text = (body or "").strip()
    if text.startswith("PDLC-REVIEW"):
        text = text.removeprefix("PDLC-REVIEW").lstrip()
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise PdlcError("review evidence is missing opening '---' metadata delimiter")
    values: dict[str, str] = {}
    for index, field in enumerate(_REVIEW_FIELDS):
        line_index = index + 1
        if line_index >= len(lines) or not lines[line_index].startswith(f"{field}:"):
            raise PdlcError(f"review evidence is missing '{field}:' metadata")
        value = lines[line_index].partition(":")[2].strip()
        if not value:
            raise PdlcError(f"review evidence has an empty '{field}:' value")
        values[field] = value
    closing_index = len(_REVIEW_FIELDS) + 1
    if closing_index >= len(lines) or lines[closing_index] != "---":
        raise PdlcError("review evidence is missing closing '---' metadata delimiter")
    try:
        verdict = ReviewVerdict(values["verdict"])
    except ValueError:
        valid = ", ".join(item.value for item in ReviewVerdict)
        raise PdlcError(f"review verdict must be one of {valid}, not {values['verdict']!r}") from None
    bounce = None if values["bounce"] == "null" else values["bounce"]
    loop = None if values["loop"] == "null" else values["loop"]
    if (bounce or loop) and verdict != ReviewVerdict.CHANGES_REQUIRED:
        raise PdlcError("review bounce metadata requires verdict Changes Required")
    if bool(bounce) != bool(loop):
        raise PdlcError("review bounce and loop must be supplied together")
    return ReviewEvidence(values["stage"], verdict, bounce, loop)
