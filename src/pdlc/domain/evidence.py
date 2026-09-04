"""Strict, typed parsers for `PDLC-REVIEW` and Verification report evidence.

`pdlc post verify` composes the Verification review body from an agent-supplied report (the
Claims Audit / User Journeys / UX / Cumulative Review sections) plus a
script-owned `### Findings` block and a `Recommendation:` line. Every reader
of that evidence — publication, Verification inspection, and Completion
inspection — parses it here so none of them accepts a shape the others
would reject.

Nothing here does I/O: it takes the comment body string and returns plain
data or raises `PdlcError`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pdlc.domain.lifecycle import PdlcError

# The four report sections the verifier always fills in.
REQUIRED_SECTIONS = ("Claims Audit", "User Journeys", "UX", "Cumulative Review")

# Sections whose every bullet is a re-verified claim and so must carry the
# script-stamped commit anchor. UX / Cumulative Review bullets are narrative.
ANCHORED_SECTIONS = ("Claims Audit", "User Journeys")

RECOMMENDATIONS = ("Approval Required", "Changes Required", "Decision Required")


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


_REVIEW_FIELDS = ("Stage", "Verdict", "Bounce", "Loop")


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
        f"Stage: {stage.strip()}",
        f"Verdict: {verdict.value}",
        f"Bounce: {bounce or 'None'}",
        f"Loop: {loop or 'None'}",
    ]
    payload = body.strip()
    return "\n".join(metadata) + (f"\n\n{payload}\n" if payload else "\n")


def parse_review(body: str) -> ReviewEvidence:
    """Parse the strict metadata prefix of a PDLC-REVIEW comment body."""
    text = (body or "").strip()
    if text.startswith("PDLC-REVIEW"):
        text = text.removeprefix("PDLC-REVIEW").lstrip()
    lines = text.splitlines()
    values: dict[str, str] = {}
    for index, field in enumerate(_REVIEW_FIELDS):
        if index >= len(lines) or not lines[index].startswith(f"{field}:"):
            raise PdlcError(f"review evidence is missing '{field}:' metadata")
        value = lines[index].partition(":")[2].strip()
        if not value:
            raise PdlcError(f"review evidence has an empty '{field}:' value")
        values[field] = value
    try:
        verdict = ReviewVerdict(values["Verdict"])
    except ValueError:
        valid = ", ".join(item.value for item in ReviewVerdict)
        raise PdlcError(f"review verdict must be one of {valid}, not {values['Verdict']!r}") from None
    bounce = None if values["Bounce"] == "None" else values["Bounce"]
    loop = None if values["Loop"] == "None" else values["Loop"]
    if (bounce or loop) and verdict != ReviewVerdict.CHANGES_REQUIRED:
        raise PdlcError("review bounce metadata requires verdict Changes Required")
    if bool(bounce) != bool(loop):
        raise PdlcError("review bounce and loop must be supplied together")
    return ReviewEvidence(values["Stage"], verdict, bounce, loop)

_ALL_SECTIONS = {name.lower(): name for name in (*REQUIRED_SECTIONS, "Findings")}

_HEADING_RE = re.compile(r"^#{1,6}\s*(.+?)\s*$")
_BULLET_RE = re.compile(r"^-\s+(.+?)\s*$")
_VERIFIED_AT_RE = re.compile(r"\(Verified @ ([^)]+)\)\s*$")
_RECOMMENDATION_RE = re.compile(r"^Recommendation:\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class EvidenceRow:
    section: str
    text: str
    commit: str | None


@dataclass(frozen=True)
class VerificationReport:
    rows: tuple[EvidenceRow, ...]
    findings: tuple[str, ...]
    recommendation: str

    def rows_in(self, section: str) -> tuple[EvidenceRow, ...]:
        return tuple(row for row in self.rows if row.section == section)

    @property
    def verified_commits(self) -> tuple[str, ...]:
        return tuple(row.commit for row in self.rows if row.commit)


def _sections(body: str) -> dict[str, list[str]]:
    """Bullets grouped by the recognised heading above them. Unknown headings
    close the current section without opening a new one."""
    found: dict[str, list[str]] = {}
    current: str | None = None
    for raw in body.splitlines():
        line = raw.strip()
        heading = _HEADING_RE.match(line)
        if heading:
            current = _ALL_SECTIONS.get(heading.group(1).lower())
            if current is not None:
                found.setdefault(current, [])
            continue
        bullet = _BULLET_RE.match(line)
        if bullet and current is not None:
            found[current].append(bullet.group(1))
    return found


def parse_verification_report(body: str) -> VerificationReport:
    """Parse an assembled verification comment body, raising `PdlcError` on any
    structural gap a downstream gate would otherwise skip over silently."""
    text = (body or "").strip()
    if not text:
        raise PdlcError("verification evidence is empty")

    sections = _sections(text)

    missing = [name for name in REQUIRED_SECTIONS if name not in sections]
    if missing:
        raise PdlcError(f"verification evidence is missing required section(s): {', '.join(missing)}")

    empty = [name for name in REQUIRED_SECTIONS if not sections[name]]
    if empty:
        raise PdlcError(f"verification evidence has no rows under: {', '.join(empty)}")

    rows: list[EvidenceRow] = []
    unanchored: list[str] = []
    for name in REQUIRED_SECTIONS:
        for item in sections[name]:
            match = _VERIFIED_AT_RE.search(item)
            commit = match.group(1).strip() if match else None
            if name in ANCHORED_SECTIONS and not commit:
                unanchored.append(f"{name}: {item}")
            rows.append(EvidenceRow(section=name, text=item, commit=commit))
    if unanchored:
        raise PdlcError(
            "verification rows missing a '(Verified @ <commit>)' anchor: " + "; ".join(unanchored)
        )

    if "Findings" not in sections:
        raise PdlcError("verification evidence is missing its '### Findings' section")

    recommendation = _RECOMMENDATION_RE.search(text)
    if not recommendation:
        raise PdlcError("verification evidence has no 'Recommendation:' line")
    if recommendation.group(1) not in RECOMMENDATIONS:
        raise PdlcError(
            f"verification recommendation must be one of {', '.join(RECOMMENDATIONS)}, "
            f"not {recommendation.group(1)!r}"
        )

    findings = tuple(item for item in sections["Findings"] if item.lower() != "none")

    return VerificationReport(
        rows=tuple(rows),
        findings=findings,
        recommendation=recommendation.group(1),
    )
