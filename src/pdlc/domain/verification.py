"""Verification reports: the `pdlc.verify/1` JSON a verifier fills in, and the
Markdown `pdlc post verify` renders from it into the Verification `PDLC-REVIEW`
comment.

The CLI owns both directions of that Markdown: `render` writes the only shape
`parse` accepts, so every reader (verify inspection, completion) reads back
exactly what publication wrote, and a hand-edited comment is refused rather
than guessed at. The verifier never writes Markdown, commit SHAs, finding IDs,
or the recommendation: `build_report` stamps HEAD and IDs and derives the
recommendation from the rows and findings.

Findings outlive the report that raised them: `ledger` replays every
parseable report in order, so a finding keeps its `F-n` ID and latest status
until a later pass marks it fixed or deferred. One HEAD per repository covers
every task, because the verifier runs on the top of each repository's task
stack; `stale_rows` narrows re-verification to the rows whose files changed
since those HEADs. The report's `head` is a HEAD spec (see `parse_heads`): the
bare SHA for a single repository, exactly as before multi-repository records.

Nothing here does I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from pdlc.domain.lifecycle import PdlcError

SCHEMA = "pdlc.verify/1"

CLAIM_RESULTS = ("confirmed", "failed", "not_run")
JOURNEY_RESULTS = ("accepted", "failed", "not_run")
UX_RESULTS = ("clean", "findings", "not_run", "not_applicable")
CUMULATIVE_RESULTS = ("clean", "findings", "not_run")
FINDING_STATUSES = ("open", "fixed", "deferred", "decision")
COMMENT_ACTIONS = ("finding", "no_action")
RECOMMENDATIONS = ("Approval Required", "Changes Required", "Decision Required")

# A row whose result is one of these needs nothing more; `failed`/`findings`
# need a finding about the row, and `not_run` needs another pass.
SETTLED_RESULTS = frozenset({"confirmed", "accepted", "clean", "not_applicable"})
FAILED_RESULTS = frozenset({"failed", "findings"})
CLOSED_STATUSES = frozenset({"fixed", "deferred"})

JOURNEYS_KEY = "journeys"
UX_KEY = "ux"
CUMULATIVE_KEY = "cumulative"
GENERAL_ABOUT = "general"

RESULTS_HEADING = "## Verification Run Results"
SECTIONS = ("Claims Audit", "User Journeys", "UX", "Cumulative Review", "Open Comments", "Findings")

_SEP = " · "
_NOTE_SEP = " — "
_HEAD_ENTRY = r"(?:[^\s@,/]+/[^\s@,/]+@)?[0-9a-f]{7,40}"
_HEADER_RE = re.compile(
    rf"^Run at (?P<run_at>.+?) · HEAD (?P<head>{_HEAD_ENTRY}(?:, {_HEAD_ENTRY})*) · (?P<recommendation>"
    + "|".join(RECOMMENDATIONS)
    + r")$"
)
_FINDING_ID_RE = re.compile(r"^F-(\d+)$")
_TOKEN_RE = re.compile(r"^\S+$")


@dataclass(frozen=True)
class Row:
    """One checked item: a task's claims, a journey, UX, or the cumulative review."""

    key: str
    result: str
    note: str = ""


@dataclass(frozen=True)
class FindingEntry:
    """One report's line about a finding. `text` (with `about`/`source`) is
    set only on the report that raised it; later reports carry status and note."""

    id: str
    status: str
    note: str = ""
    about: str = GENERAL_ABOUT
    text: str | None = None
    source: str = ""

    @property
    def raised(self) -> bool:
        return self.text is not None


@dataclass(frozen=True)
class CommentAction:
    url: str
    action: str
    note: str = ""


@dataclass(frozen=True)
class Report:
    head: str
    run_at: str
    recommendation: str
    claims: tuple[Row, ...]
    journeys: tuple[Row, ...] | None  # None when the record has no UI task
    ux: Row
    cumulative: Row
    comments: tuple[CommentAction, ...] = ()
    findings: tuple[FindingEntry, ...] = ()

    def rows(self) -> list[tuple[str, Row]]:
        """Every checked row, qualified by its section."""
        rows = [("claims", row) for row in self.claims]
        rows += [("journeys", row) for row in self.journeys or ()]
        return rows + [("ux", self.ux), ("cumulative", self.cumulative)]


@dataclass(frozen=True)
class Finding:
    """A finding's current state across every report so far."""

    id: str
    about: str
    text: str
    source: str
    status: str
    note: str
    raised_at: str


@dataclass(frozen=True)
class Decision:
    finding: str
    text: str
    question: str
    options: tuple[str, ...]
    recommendation: str
    blocks: str
    why: str


@dataclass(frozen=True)
class VerifyContext:
    """What the record requires of this report, resolved by the command."""

    head: str
    run_at: str
    tasks: tuple[str, ...]  # closed delivery tasks, each needing a claims row
    journeys: tuple[str, ...] | None  # UJ ids, or None when no task is UI
    open_comments: tuple[str, ...]  # URLs of still-unresolved review comments
    findings: dict[str, Finding] = field(default_factory=dict)  # ledger before this report


@dataclass(frozen=True)
class Built:
    """A validated report plus the side effects its publication owes."""

    report: Report
    decisions: tuple[Decision, ...]
    deferred: tuple[str, ...]  # Open Questions lines, without the `Deferred — ` marker
    bounce: str | None


# --- HEAD specs ---------------------------------------------------------------


def parse_heads(spec: str) -> dict[str, str]:
    """A report's HEAD spec as `{repository: sha}`. The spec is comma-separated
    `[owner/name@]sha` entries; an unqualified entry, keyed "", is the code
    repository's, so a single-repository spec is just its SHA."""
    heads: dict[str, str] = {}
    for entry in spec.split(", "):
        repository, _, sha = entry.rpartition("@")
        heads[repository.casefold()] = sha
    return heads


def format_heads(heads: dict[str, str]) -> str:
    """The inverse of `parse_heads`: the code repository's ("" key) first and
    unqualified, every other repository's after it in name order."""
    return ", ".join(
        sha if not repository else f"{repository}@{sha}"
        for repository, sha in sorted(heads.items(), key=lambda item: (item[0] != "", item[0]))
    )


def short_heads(spec: str) -> str:
    """A HEAD spec with every SHA cut to 12 characters, for display."""
    return format_heads({repository: sha[:12] for repository, sha in parse_heads(spec).items()})


# --- ledger and staleness ---------------------------------------------------


def ledger(reports: Iterable[Report]) -> dict[str, Finding]:
    """Every finding's latest state, replaying `reports` oldest first."""
    found: dict[str, Finding] = {}
    for report in reports:
        for entry in report.findings:
            if entry.raised:
                found[entry.id] = Finding(
                    entry.id, entry.about, entry.text or "", entry.source, entry.status, entry.note, report.head,
                )
            elif entry.id in found:
                found[entry.id] = replace(found[entry.id], status=entry.status, note=entry.note)
    return found


def stale_rows(
    report: Report,
    changed: set[str] | None,
    task_files: dict[str, set[str] | None],
    ui_tasks: set[str],
) -> set[tuple[str, str]]:
    """`(section, key)` of every row in `report` that no longer holds.

    `changed` is every file that differs between the report's HEAD and now, or
    None when that HEAD cannot be read (everything is stale). A task's claims
    row is stale when its PR files changed (or are unknown); journeys and UX
    when any UI task is stale or new; the cumulative review on any change.
    """
    rows = report.rows()
    if changed is None:
        return {(section, row.key) for section, row in rows}
    stale: set[tuple[str, str]] = set()
    claimed = {row.key for row in report.claims}
    for row in report.claims:
        files = task_files.get(row.key)
        if files is None or files & changed:
            stale.add(("claims", row.key))
    ui_stale = any(task not in claimed or ("claims", task) in stale for task in ui_tasks)
    if ui_stale:
        stale |= {(section, row.key) for section, row in rows if section in ("journeys", "ux")}
    if changed:
        stale.add(("cumulative", report.cumulative.key))
    return stale


def blocking_rows(report: Report, findings: dict[str, Finding]) -> list[str]:
    """Rows that keep `report` from being clean: not run, or failed without
    every finding about them deferred."""
    blocking = []
    for section, row in report.rows():
        if row.result == "not_run":
            blocking.append(f"{section} {row.key}: not run")
        elif row.result in FAILED_RESULTS:
            about = [f for f in findings.values() if f.about == row.key]
            if not about or any(f.status != "deferred" for f in about):
                blocking.append(f"{section} {row.key}: {row.result}")
    return blocking


def derive_recommendation(report: Report, findings: dict[str, Finding]) -> str:
    if any(f.status == "decision" for f in findings.values()):
        return "Decision Required"
    if any(f.status == "open" for f in findings.values()) or blocking_rows(report, findings):
        return "Changes Required"
    return "Approval Required"


# --- building a report from verifier JSON -------------------------------------


def build_report(data: Any, context: VerifyContext) -> Built:
    """Validate verifier JSON against `context` and build the report.

    Every problem is collected and raised together, so one refusal lists
    everything the verifier must fix.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        raise PdlcError("verification report must be a JSON object")
    if data.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")

    claims = _rows(data.get("claims"), "claims", "task", context.tasks, CLAIM_RESULTS, errors)
    journeys: tuple[Row, ...] | None = None
    if context.journeys is None:
        if data.get("journeys"):
            errors.append("journeys must be null: no delivery task is UI")
    else:
        journeys = _rows(data.get("journeys"), "journeys", "journey", context.journeys, JOURNEY_RESULTS, errors)
    ux = _single(data.get("ux"), "ux", UX_KEY, UX_RESULTS, errors, default="not_applicable" if context.journeys is None else None)
    if context.journeys is None and ux.result not in ("not_applicable", ""):
        errors.append("ux.result must be not_applicable: no delivery task is UI")
    if context.journeys is not None and ux.result == "not_applicable":
        errors.append("ux.result cannot be not_applicable while a delivery task is UI")
    cumulative = _single(data.get("cumulativeReview"), "cumulativeReview", CUMULATIVE_KEY, CUMULATIVE_RESULTS, errors)

    comments = _comments(data.get("openComments"), context.open_comments, errors)
    updates = _updates(data.get("findings"), context.findings, errors)
    raised = _raised(data.get("newFindings"), context.findings, errors)

    entries = [entry for entry, _ in updates] + [entry for entry, _ in raised]
    for comment in comments:
        if comment.action == "finding" and not any(entry.raised and entry.source == comment.url for entry in entries):
            errors.append(f"openComments {comment.url}: action is finding, but no newFindings entry has it as source")

    current = dict(context.findings)
    for entry in entries:
        current[entry.id] = Finding(
            entry.id,
            entry.about if entry.raised else current[entry.id].about,
            entry.text if entry.text is not None else current[entry.id].text,
            entry.source if entry.raised else current[entry.id].source,
            entry.status,
            entry.note,
            context.head if entry.raised else current[entry.id].raised_at,
        )
    for finding in context.findings.values():
        if finding.status == "decision" and not any(entry.id == finding.id for entry in entries):
            errors.append(f"findings {finding.id}: it went to the driver as a decision; record its outcome (open, fixed, deferred)")

    draft = Report(
        head=context.head, run_at=context.run_at, recommendation="Changes Required",
        claims=claims, journeys=journeys, ux=ux, cumulative=cumulative,
        comments=tuple(comments), findings=tuple(entries),
    )
    for section, row in draft.rows():
        if row.result in FAILED_RESULTS and not any(
            f.about == row.key and f.status in ("open", "deferred", "decision") for f in current.values()
        ):
            errors.append(f"{section} {row.key}: result {row.result} needs an open, deferred, or decision finding about {row.key}")

    recommendation = derive_recommendation(draft, current)
    bounce = data.get("bounce")
    if bounce is not None and (not isinstance(bounce, str) or not bounce.strip()):
        errors.append("bounce must be a stage name or null")
        bounce = None
    if bounce and recommendation != "Changes Required":
        errors.append(f"bounce is only valid when the report needs changes; this report derives {recommendation}")

    if errors:
        raise PdlcError("verification report is not valid:\n" + "\n".join(f"  - {error}" for error in errors))

    decisions = tuple(decision for _, decision in [*updates, *raised] if decision is not None)
    previously = {fid: finding.status for fid, finding in context.findings.items()}
    deferred = tuple(
        f"{entry.id}: {current[entry.id].text} ({entry.note})"
        for entry in entries
        if entry.status == "deferred" and previously.get(entry.id) != "deferred"
    )
    return Built(replace(draft, recommendation=recommendation), decisions, deferred, bounce.strip() if bounce else None)


def _text(value: Any) -> str:
    """One line of prose: every run of whitespace collapsed to a space."""
    return " ".join(value.split()) if isinstance(value, str) else ""


def _result(value: Any, allowed: tuple[str, ...], where: str, errors: list[str]) -> str:
    if value not in allowed:
        errors.append(f"{where}.result must be one of {', '.join(allowed)}, not {value!r}")
        return ""
    return str(value)


def _rows(
    value: Any, section: str, key_field: str, expected: tuple[str, ...], allowed: tuple[str, ...], errors: list[str],
) -> tuple[Row, ...]:
    items = value if isinstance(value, list) else []
    if value is not None and not isinstance(value, list):
        errors.append(f"{section} must be an array")
    rows: dict[str, Row] = {}
    for index, item in enumerate(items):
        where = f"{section}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        key = item.get(key_field)
        if not isinstance(key, str) or key not in expected:
            errors.append(f"{where}.{key_field} {key!r} is not one of this record's {section}: {', '.join(expected) or 'none'}")
            continue
        if key in rows:
            errors.append(f"{where}.{key_field} {key} is listed twice")
            continue
        rows[key] = Row(key, _result(item.get("result"), allowed, where, errors), _text(item.get("note")))
    missing = [key for key in expected if key not in rows]
    if missing:
        errors.append(f"{section} is missing a row for: {', '.join(missing)}")
    return tuple(rows[key] for key in expected if key in rows)


def _single(
    value: Any, name: str, key: str, allowed: tuple[str, ...], errors: list[str], *, default: str | None = None,
) -> Row:
    if value is None and default is not None:
        return Row(key, default)
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object")
        return Row(key, "")
    note = _text(value.get("note"))
    scope = _text(value.get("scope"))
    if scope:
        note = f"{scope}; {note}" if note else scope
    return Row(key, _result(value.get("result"), allowed, name, errors), note)


def _comments(value: Any, live: tuple[str, ...], errors: list[str]) -> list[CommentAction]:
    given: dict[str, CommentAction] = {}
    for index, item in enumerate(value if isinstance(value, list) else []):
        where = f"openComments[{index}]"
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            errors.append(f"{where} must be an object with a url")
            continue
        action = item.get("action")
        note = _text(item.get("note"))
        if action not in COMMENT_ACTIONS:
            errors.append(f"{where}.action must be one of {', '.join(COMMENT_ACTIONS)}, not {action!r}")
            continue
        if action == "no_action" and not note:
            errors.append(f"{where}: no_action needs a note saying why")
        given[item["url"]] = CommentAction(item["url"], str(action), note)
    missing = [url for url in live if url not in given]
    if missing:
        errors.append("openComments has no action for: " + ", ".join(missing))
    # A comment resolved since inspection needs no action and is dropped.
    return [given[url] for url in live if url in given]


def _status(item: dict, where: str, errors: list[str], *, allowed: tuple[str, ...] = FINDING_STATUSES) -> str:
    status = item.get("status")
    if status not in allowed:
        errors.append(f"{where}.status must be one of {', '.join(allowed)}, not {status!r}")
        return ""
    if status == "deferred" and not _text(item.get("note")):
        errors.append(f"{where}: deferred needs a note with the driver's reason")
    return str(status)


def _decision(item: dict, finding: str, text: str, where: str, errors: list[str]) -> Decision | None:
    if item.get("status") != "decision":
        if item.get("decision"):
            errors.append(f"{where}.decision is only valid with status decision")
        return None
    block = item.get("decision")
    if not isinstance(block, dict):
        errors.append(f"{where}: status decision needs a decision object")
        return None
    fields = {name: _text(block.get(name)) for name in ("question", "recommendation", "blocks", "whyNotMechanical")}
    options = tuple(_text(option) for option in block.get("options") or [] if _text(option))
    for name, value in fields.items():
        if not value:
            errors.append(f"{where}.decision.{name} is required")
    if len(options) < 2:
        errors.append(f"{where}.decision.options needs at least two options")
    return Decision(finding, text, fields["question"], options, fields["recommendation"], fields["blocks"], fields["whyNotMechanical"])


def _updates(value: Any, known: dict[str, Finding], errors: list[str]) -> list[tuple[FindingEntry, Decision | None]]:
    updates: list[tuple[FindingEntry, Decision | None]] = []
    seen: set[str] = set()
    for index, item in enumerate(value if isinstance(value, list) else []):
        where = f"findings[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        fid = item.get("id")
        if not isinstance(fid, str) or fid not in known:
            errors.append(f"{where}.id {fid!r} is not a finding on this record")
            continue
        if fid in seen:
            errors.append(f"{where}.id {fid} is listed twice")
            continue
        seen.add(fid)
        status = _status(item, where, errors)
        decision = _decision(item, fid, known[fid].text, where, errors)
        updates.append((FindingEntry(fid, status, _text(item.get("note"))), decision))
    return updates


def _raised(value: Any, known: dict[str, Finding], errors: list[str]) -> list[tuple[FindingEntry, Decision | None]]:
    numbers = [int(match.group(1)) for fid in known if (match := _FINDING_ID_RE.match(fid))]
    next_number = max(numbers, default=0) + 1
    raised: list[tuple[FindingEntry, Decision | None]] = []
    for index, item in enumerate(value if isinstance(value, list) else []):
        where = f"newFindings[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        text = _text(item.get("text"))
        if not text:
            errors.append(f"{where}.text is required")
        about = _text(item.get("about")) or GENERAL_ABOUT
        if not _TOKEN_RE.match(about):
            errors.append(f"{where}.about must be one token, such as a task id, journey id, ux, or cumulative")
        source = _text(item.get("source"))
        status = _status(item, where, errors, allowed=("open", "deferred", "decision"))
        fid = f"F-{next_number}"
        next_number += 1
        decision = _decision(item, fid, text, where, errors)
        raised.append((FindingEntry(fid, status, _text(item.get("note")), about, text, source), decision))
    return raised


# --- Markdown ---------------------------------------------------------------


def render(report: Report) -> str:
    """The report as the Markdown body of a Verification `PDLC-REVIEW` comment."""
    lines = [RESULTS_HEADING, f"Run at {report.run_at}{_SEP}HEAD {report.head}{_SEP}{report.recommendation}"]

    def section(name: str, rows: list[str]) -> None:
        lines.extend(["", f"### {name}", ""])
        lines.extend(rows or ["None"])

    section("Claims Audit", [_row(row) for row in report.claims])
    section("User Journeys", [_row(row) for row in report.journeys] if report.journeys is not None else [_row(Row(JOURNEYS_KEY, "not_applicable"))])
    section("UX", [_row(report.ux)])
    section("Cumulative Review", [_row(report.cumulative)])
    if report.comments:
        section("Open Comments", [_row(Row(c.url, c.action, c.note)) for c in report.comments])
    finding_lines: list[str] = []
    for entry in report.findings:
        if entry.raised:
            finding_lines.append(f"- {entry.id}{_SEP}{entry.status}{_SEP}{entry.about}{_NOTE_SEP}{entry.text}")
            if entry.source:
                finding_lines.append(f"  - source: {entry.source}")
            if entry.note:
                finding_lines.append(f"  - note: {entry.note}")
        else:
            finding_lines.append(_row(Row(entry.id, entry.status, entry.note)))
    section("Findings", finding_lines)
    return "\n".join(lines) + "\n"


def render_decisions(decisions: Iterable[Decision]) -> str:
    """`## Decision Required` blocks for the record's decision blocker."""
    blocks = [
        "\n".join([
            "## Decision Required",
            "",
            f"Finding: {d.finding} — {d.text}",
            f"Question: {d.question}",
            f"Options: {' / '.join(d.options)}",
            f"Recommendation: {d.recommendation}",
            f"Blocks: {d.blocks}",
            f"Why not mechanical: {d.why}",
        ])
        for d in decisions
    ]
    return "\n\n".join(blocks) + "\n"


def _row(row: Row) -> str:
    return f"- {row.key}{_SEP}{row.result}" + (f"{_NOTE_SEP}{row.note}" if row.note else "")


def parse(body: str) -> Report:
    """Read back a report `render` wrote, raising `PdlcError` on any other shape
    (including reports from before `pdlc.verify/1`)."""
    text = body or ""
    start = text.find(RESULTS_HEADING)
    if start < 0:
        raise PdlcError(f"verification report has no '{RESULTS_HEADING}' heading")
    lines = [line.rstrip() for line in text[start:].splitlines()[1:]]
    header = next((line for line in lines if line.strip()), "")
    match = _HEADER_RE.match(header)
    if not match:
        raise PdlcError("verification report header is not 'Run at <time> · HEAD <sha> · <recommendation>' (a report from before pdlc.verify/1 needs a fresh pass)")

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[lines.index(header) + 1:]:
        if not line.strip():
            continue
        if line.startswith("### "):
            current = line[4:].strip()
            if current not in SECTIONS:
                raise PdlcError(f"verification report has an unknown section {current!r}")
            sections[current] = []
        elif current is None:
            raise PdlcError(f"verification report has text outside a section: {line!r}")
        else:
            sections[current].append(line)
    for name in SECTIONS:
        if name != "Open Comments" and name not in sections:
            raise PdlcError(f"verification report is missing its '### {name}' section")

    claims = tuple(_parse_row(line, "Claims Audit") for line in _bullets(sections["Claims Audit"]))
    journey_rows = tuple(_parse_row(line, "User Journeys") for line in _bullets(sections["User Journeys"]))
    journeys: tuple[Row, ...] | None = journey_rows
    if journey_rows == (Row(JOURNEYS_KEY, "not_applicable"),):
        journeys = None
    ux = _only_row(sections["UX"], "UX")
    cumulative = _only_row(sections["Cumulative Review"], "Cumulative Review")
    comments = tuple(
        CommentAction(row.key, row.result, row.note)
        for row in (_parse_row(line, "Open Comments") for line in _bullets(sections.get("Open Comments", [])))
    )
    return Report(
        head=match["head"], run_at=match["run_at"], recommendation=match["recommendation"],
        claims=claims, journeys=journeys, ux=ux, cumulative=cumulative,
        comments=comments, findings=_parse_findings(sections["Findings"]),
    )


def _bullets(lines: list[str]) -> list[str]:
    if lines == ["None"]:
        return []
    for line in lines:
        if not line.startswith("- "):
            raise PdlcError(f"verification report line is not a '- ' row: {line!r}")
    return lines


def _parse_row(line: str, section: str) -> Row:
    head, _, note = line[2:].partition(_NOTE_SEP)
    parts = head.split(_SEP)
    if len(parts) != 2 or not all(parts):
        raise PdlcError(f"{section} row is not '- <key> · <result> — <note>': {line!r}")
    return Row(parts[0], parts[1], note)


def _only_row(lines: list[str], section: str) -> Row:
    rows = _bullets(lines)
    if len(rows) != 1:
        raise PdlcError(f"verification report's {section} section must hold exactly one row")
    return _parse_row(rows[0], section)


def _parse_findings(lines: list[str]) -> tuple[FindingEntry, ...]:
    if lines == ["None"]:
        return ()
    entries: list[FindingEntry] = []
    for line in lines:
        if line.startswith("  - ") and entries and entries[-1].raised:
            name, _, value = line[4:].partition(": ")
            if name not in ("source", "note"):
                raise PdlcError(f"Findings detail must be 'source:' or 'note:': {line!r}")
            entries[-1] = replace(entries[-1], **{name: value})
            continue
        if not line.startswith("- "):
            raise PdlcError(f"Findings line is not a '- ' row: {line!r}")
        head, _, rest = line[2:].partition(_NOTE_SEP)
        parts = head.split(_SEP)
        if not _FINDING_ID_RE.match(parts[0]) or len(parts) not in (2, 3) or parts[1] not in FINDING_STATUSES:
            raise PdlcError(f"Findings row is not '- F-<n> · <status>[ · <about>] — <text>': {line!r}")
        if len(parts) == 3:
            entries.append(FindingEntry(parts[0], parts[1], about=parts[2], text=rest))
        else:
            entries.append(FindingEntry(parts[0], parts[1], note=rest))
    return tuple(entries)
