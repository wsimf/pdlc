"""The task reviewer's findings file, split by the agent that fixes each finding.

The reviewer fills an outline with one `### ` section per owner plus a verdict.
The implementer brief carries the implementation findings and the test-writer
brief carries both, so each section is routed without the caller reading it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pdlc.domain.lifecycle import PdlcError

IMPLEMENTATION = "Implementation findings"
TEST = "Test findings"
VERDICT = "Verdict"
VERDICTS = ("Changes Required", "Approval Required")

_BLOCKING = re.compile(r"\[blocking\]", re.IGNORECASE)


@dataclass(frozen=True)
class ImplementFindings:
    """One review's findings; a section with no findings is ""."""

    implementation: str
    test: str
    verdict: str

    @property
    def implementation_blocking(self) -> bool:
        return bool(_BLOCKING.search(self.implementation))


def _sections(text: str) -> dict[str, list[str]]:
    """Every `### ` section's lines, keyed by heading; fenced headings are content."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    fence = False
    for line in text.splitlines():
        if line.startswith("```") or line.startswith("~~~"):
            fence = not fence
        elif not fence and line.startswith("### "):
            current = sections.setdefault(line[4:].strip(), [])
            continue
        if current is not None:
            current.append(line)
    return sections


def _findings(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    return "" if text.lower() in ("", "none") else text


def parse(text: str, source: str) -> ImplementFindings:
    """The findings in `text`, or a refusal naming what `source` is missing."""
    sections = _sections(text)
    missing = [name for name in (IMPLEMENTATION, TEST, VERDICT) if name not in sections]
    if missing:
        raise PdlcError(
            f"{source} is not a task review findings file: missing "
            + ", ".join(f"`### {name}`" for name in missing)
        )
    verdict = _findings(sections[VERDICT])
    if verdict not in VERDICTS:
        raise PdlcError(f"{source} has no verdict: `### {VERDICT}` must read one of {', '.join(VERDICTS)}")
    return ImplementFindings(_findings(sections[IMPLEMENTATION]), _findings(sections[TEST]), verdict)
