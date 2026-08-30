"""Strict, typed parser for the `PDLC-COMPLETE` evidence body.

`pdlc-post-complete.py` is the only writer of a completion record. It merges
what used to be two skill steps — reconciling the parent body and locking the
record — into one call, and it never edits the parent body except to blank
the now-settled `## Open Questions` section. Everything a reader needs about
what shipped, which decisions emerged during delivery, and how each open
question resolved therefore lives in this one comment, so it is parsed here
with the same rigour `evidence.py` applies to verification evidence.

Nothing here does I/O: it takes the comment body string and returns plain
data or raises `PdlcError`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pdlc.pdlc_common import PdlcError

# Every completion evidence body carries these sections, in any order, each
# with at least one non-empty line.
REQUIRED_SECTIONS = ("Shipped", "Verification", "Decisions", "Open Questions", "Limitations", "Skipped Stages")

# Sections whose only permitted "nothing to record" value is a lone `None`
# bullet — an empty list would be ambiguous with an omission.
NILABLE_SECTIONS = ("Decisions", "Open Questions", "Limitations", "Skipped Stages")

_SECTION_LOOKUP = {name.lower(): name for name in REQUIRED_SECTIONS}

_HEADING_RE = re.compile(r"^#{1,6}\s*(.+?)\s*$")
_BULLET_RE = re.compile(r"^-\s+(.+?)\s*$")
_VERIFICATION_RE = re.compile(r"clean\s+@\s+(\S+)", re.IGNORECASE)
# "<question text> — Resolved: <answer>" / "<question text> — Deferred: <what>"
_DISPOSITION_RE = re.compile(r"^(?P<question>.+?)\s*[—:-]\s*(?P<kind>Resolved|Deferred)\b", re.IGNORECASE)


def normalize_question(text: str) -> str:
    """Collapse a question to a stable key for matching a body Open Questions
    entry against its disposition line: lowercase, whitespace-collapsed, and
    stripped of surrounding punctuation and a leading `Deferred —` marker."""
    lowered = re.sub(r"\s+", " ", text.strip().lower())
    lowered = re.sub(r"^deferred\s*[—:-]\s*", "", lowered)
    return lowered.strip(" .?!\"'`—-")


@dataclass(frozen=True)
class CompletionReport:
    verified_commit: str
    decisions: tuple[str, ...]
    dispositioned_questions: tuple[str, ...]
    limitations: tuple[str, ...]
    skipped_stages: tuple[str, ...]

    @property
    def dispositions_all(self) -> bool:
        """True when the Open Questions section is a lone `None` — the record
        carried no live question to dispose of."""
        return not self.dispositioned_questions


def _sections(body: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    current: str | None = None
    for raw in body.splitlines():
        line = raw.strip()
        heading = _HEADING_RE.match(line)
        if heading:
            current = _SECTION_LOOKUP.get(heading.group(1).lower())
            if current is not None:
                found.setdefault(current, [])
            continue
        if current is not None and line:
            found[current].append(line)
    return found


def _bullets(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        bullet = _BULLET_RE.match(line)
        if bullet:
            out.append(bullet.group(1).strip())
    return out


def parse_completion_report(body: str) -> CompletionReport:
    """Parse an assembled completion evidence body, raising `PdlcError` on any
    structural gap a completion gate would otherwise skip over silently."""
    text = (body or "").strip()
    if not text:
        raise PdlcError("completion evidence is empty")

    sections = _sections(text)

    missing = [name for name in REQUIRED_SECTIONS if name not in sections]
    if missing:
        raise PdlcError(f"completion evidence is missing required section(s): {', '.join(missing)}")

    empty = [name for name in REQUIRED_SECTIONS if not sections[name]]
    if empty:
        raise PdlcError(f"completion evidence has no content under: {', '.join(empty)}")

    verification_match = _VERIFICATION_RE.search(" ".join(sections["Verification"]))
    if not verification_match:
        raise PdlcError("completion evidence Verification section needs a 'clean @ <commit>' reference")

    def nilable(name: str) -> tuple[str, ...]:
        bullets = _bullets(sections[name])
        if not bullets:
            raise PdlcError(f"completion evidence '{name}' must be a bulleted list, or a lone '- None'")
        if len(bullets) == 1 and bullets[0].strip().lower() == "none":
            return ()
        return tuple(bullets)

    decisions = nilable("Decisions")
    limitations = nilable("Limitations")
    skipped_stages = nilable("Skipped Stages")

    question_bullets = _bullets(sections["Open Questions"])
    if not question_bullets:
        raise PdlcError("completion evidence 'Open Questions' must be a bulleted list, or a lone '- None'")
    if len(question_bullets) == 1 and question_bullets[0].strip().lower() == "none":
        dispositioned: tuple[str, ...] = ()
    else:
        keys = []
        for bullet in question_bullets:
            disposition = _DISPOSITION_RE.match(bullet)
            if not disposition:
                raise PdlcError(
                    f"completion evidence Open Questions entry is not a disposition "
                    f"(expected '<question> — Resolved: ...' or '— Deferred: ...'): {bullet!r}"
                )
            keys.append(normalize_question(disposition.group("question")))
        dispositioned = tuple(keys)

    return CompletionReport(
        verified_commit=verification_match.group(1),
        decisions=decisions,
        dispositioned_questions=dispositioned,
        limitations=limitations,
        skipped_stages=skipped_stages,
    )


def live_open_questions(open_questions_section: str) -> list[str]:
    """The unresolved entries in the parent body's `## Open Questions` section:
    real bullets that are not a `none`/`n/a` placeholder and not already an
    explicit `Deferred` deferral carried over from pdlc-verify."""
    live = []
    for raw in open_questions_section.splitlines():
        line = raw.strip()
        if not line.startswith("-"):
            continue
        entry = line.lstrip("- ").strip()
        low = entry.lower()
        if low in ("none", "n/a") or low.startswith("deferred"):
            continue
        live.append(entry)
    return live


def undispositioned_questions(report: CompletionReport, open_questions_section: str) -> list[str]:
    """Live parent Open Questions entries that the completion evidence does not
    account for. A lone `- None` in the evidence disposes of nothing, so any
    live entry is then undispositioned."""
    live = live_open_questions(open_questions_section)
    if not live:
        return []
    if report.dispositions_all:
        return live
    keys = report.dispositioned_questions
    unaccounted = []
    for entry in live:
        key = normalize_question(entry)
        if not any(key == k or key in k or k in key for k in keys):
            unaccounted.append(entry)
    return unaccounted
