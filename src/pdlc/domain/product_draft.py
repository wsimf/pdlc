"""Pure policy for a Product draft on its way to landing.

A draft passes through two reviews: the product pass reviews everything but
the `### Technical approach` subsection, a feasibility spike then writes that
subsection against the reviewed product content, and the technical pass
reviews the whole draft. `Stamp` holds a fingerprint of what each step saw;
`phase` compares those fingerprints and the two review verdicts with the draft
as it is now to name the one step due next. Any change to the product content
after a step sends the draft back through that step.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import re

# A work item's slug: stamped once at creation and never rewritten.
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

TECHNICAL_APPROACH = "Technical approach"
ASSUMPTIONS = "Assumptions"

NOT_FEASIBLE = "Not feasible"
FEASIBILITY_VERDICTS = ("Feasible", "Feasible with caveats", NOT_FEASIBLE)

NEEDS_REVISION = "Needs Revision"
READY_TO_LAND = "Ready to Land"

_FEASIBILITY_RE = re.compile(r"^Verdict:\s*(.+?)\s*$", re.MULTILINE)
_REVIEW_VERDICT_RE = re.compile(r"^Verdict:\s*(Needs Revision|Ready to Land)\s*$", re.MULTILINE)
# A finding opens with its bullet and ID, e.g. `- F3 [P1] FR-2 — "..."`.
_FINDING_RE = re.compile(r"^[-*]\s+(F\d+)\b")
_AUTHOR_RESPONSE_RE = re.compile(r"^Author response:\s*(Fixed|Rejected)\s*[—–-]\s*\S", re.IGNORECASE)
_HEADING_RE = re.compile(r"^(#{1,6})\s")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


class Phase(StrEnum):
    """The step a Product draft is due for, in the order a draft passes through them."""

    DRAFT = "draft"
    PRODUCT_REVIEW = "product review"
    PRODUCT_FINDINGS = "product findings"
    SPIKE = "feasibility spike"
    NOT_FEASIBLE = "not feasible"
    TECHNICAL_REVIEW = "technical review"
    TECHNICAL_FINDINGS = "technical findings"
    READY = "ready to land"


@dataclass(frozen=True)
class Stamp:
    """Fingerprints of what each step saw: the product content the product
    reviewer and the spike were handed, and the whole draft the technical
    reviewer was handed. `None` when that step has not run since it was reset."""

    product: str | None = None
    spiked: str | None = None
    technical: str | None = None


def fingerprint(text: str) -> str:
    """A stable fingerprint that ignores trailing whitespace at line ends and the end."""
    normalized = "\n".join(line.rstrip() for line in text.strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _product_span(lines: list[str], name: str) -> tuple[int, int] | None:
    """Line range of the `### name` subsection of `## Product`, heading included."""
    fenced = False
    in_product = False
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = _HEADING_RE.match(line)
        if not heading:
            continue
        level = len(heading.group(1))
        if start is not None and level <= 3:
            return start, index
        if level == 2:
            in_product = line.rstrip() == "## Product"
        elif level == 3 and in_product and line[4:].strip() == name:
            start = index
    return (start, len(lines)) if start is not None else None


def subsection(draft: str, name: str) -> str | None:
    """The content of `## Product`'s `### name` subsection without its HTML
    comments, or `None` when absent. A heading holding only a placeholder
    comment, as the blank draft seeds `### Technical approach`, reads as ""."""
    lines = draft.splitlines()
    span = _product_span(lines, name)
    return None if span is None else _COMMENT_RE.sub("", "\n".join(lines[span[0] + 1:span[1]])).strip()


def product_content(draft: str) -> str:
    """The draft without its `### Technical approach` subsection: what the product pass reviews."""
    lines = draft.splitlines()
    span = _product_span(lines, TECHNICAL_APPROACH)
    if span is not None:
        lines = lines[:span[0]] + lines[span[1]:]
    return "\n".join(lines)


def feasibility_verdict(approach: str) -> str | None:
    """The approach's `Verdict:` value, or `None` when it states none."""
    match = _FEASIBILITY_RE.search(approach)
    return match.group(1) if match else None


def review_verdict(findings: str) -> str | None:
    """A filled findings file's verdict, or `None` while it still holds the outline."""
    matches = _REVIEW_VERDICT_RE.findall(findings)
    return matches[-1] if matches else None


def missing_author_responses(findings: str) -> list[str]:
    """IDs of the findings that carry no `Author response: Fixed|Rejected — ...` line."""
    missing: list[str] = []
    current: str | None = None
    answered = False
    for raw in findings.splitlines():
        line = raw.strip()
        # The outline's own layout example is not a finding.
        finding = _FINDING_RE.match(line) if "[P0–P3]" not in line else None
        if finding or _HEADING_RE.match(line):
            if current is not None and not answered:
                missing.append(current)
            current, answered = (finding.group(1), False) if finding else (None, False)
            continue
        if current is not None and _AUTHOR_RESPONSE_RE.match(line):
            answered = True
    if current is not None and not answered:
        missing.append(current)
    return missing


def land_problems(draft: str) -> list[str]:
    """What keeps the draft's content from landing, beyond the approach template."""
    problems: list[str] = []
    approach = subsection(draft, TECHNICAL_APPROACH)
    if approach is None:
        problems.append(f"missing subsection: ### {TECHNICAL_APPROACH} (the last subsection of ## Product)")
    elif not approach:
        problems.append(f"### {TECHNICAL_APPROACH} is empty; the feasibility spike writes it")
    else:
        verdict = feasibility_verdict(approach)
        if verdict is None:
            problems.append(f"### {TECHNICAL_APPROACH} states no `Verdict:` line")
        elif verdict not in FEASIBILITY_VERDICTS:
            problems.append(f"feasibility verdict must be one of {', '.join(FEASIBILITY_VERDICTS)}; found {verdict!r}")
        elif verdict == NOT_FEASIBLE:
            problems.append("the feasibility verdict is Not feasible; revise the product with the driver until it is feasible")
    if subsection(draft, ASSUMPTIONS) is not None:
        problems.append(
            f"### {ASSUMPTIONS} must be resolved before landing: confirm each one and fold it into a requirement or"
            " constraint, or settle it with the driver"
        )
    return problems


def phase(draft: str, stamp: Stamp, product_verdict: str | None, technical_verdict: str | None) -> Phase:
    """The one step due next for `draft`, given what each step last saw and the reviews' verdicts."""
    product = fingerprint(product_content(draft))
    if stamp.product is None:
        return Phase.DRAFT
    if stamp.product != product or product_verdict is None:
        return Phase.PRODUCT_REVIEW
    if product_verdict == NEEDS_REVISION:
        return Phase.PRODUCT_FINDINGS
    approach = subsection(draft, TECHNICAL_APPROACH)
    if not approach or stamp.spiked != product:
        return Phase.SPIKE
    if feasibility_verdict(approach) == NOT_FEASIBLE:
        return Phase.NOT_FEASIBLE
    if stamp.technical != fingerprint(draft) or technical_verdict is None:
        return Phase.TECHNICAL_REVIEW
    if technical_verdict == NEEDS_REVISION:
        return Phase.TECHNICAL_FINDINGS
    return Phase.READY
