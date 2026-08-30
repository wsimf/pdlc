"""PDLC-generic primitives shared across the pdlc scripts: the error type,
evidence markers, the fixed stage order, and local file/stdin handling. No
backend I/O here — the `workitem_host` and `code_host` packages own that.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


class PdlcError(RuntimeError):
    """A user-facing pdlc failure. Callers catch this at the CLI boundary,
    print str(error) to stderr, and exit 1 — mirroring the shell `die`."""


# True when the script was invoked with no arguments or an explicit -h/--help
# flag anywhere in the argument list, so a caller unsure of positional
# arguments can recover its usage from the module docstring instead of guessing.
def wants_help(argv: list[str]) -> bool:
    return not argv or any(argument in ("-h", "--help") for argument in argv)


def print_help(doc: str | None) -> None:
    print((doc or "").strip())


# Evidence markers

# Every evidence comment opens with its marker so orientation can tell a
# durable PDLC record from ordinary Issue chatter. The marker is stamped by
# the calling script from its own knowledge of the stage, so no agent ever has
# to write one or remember the vocabulary.
MARKERS = [
    "PRODUCT", "UI", "TASKS", "PLAN", "IMPLEMENTATION",
    "TESTING", "VERIFICATION", "COMPLETE",
    "APPROVED", "AUTOAPPROVED", "INVALIDATED", "SKIPPED", "DECISION", "RESOLUTION",
]


def require_marker(candidate: str | None) -> None:
    valid = " ".join(MARKERS)
    if not candidate:
        raise PdlcError(f"an evidence marker is required; valid markers: {valid}")
    if candidate not in MARKERS:
        raise PdlcError(f"unknown evidence marker: {candidate}; valid markers: {valid}")


# The marker a stage's own evidence carries.
_MARKER_FOR_STAGE = {
    "Product": "PRODUCT",
    "UI": "UI",
    "Tasks": "TASKS",
    "Technical Plan": "PLAN",
    "Implementation": "IMPLEMENTATION",
    "Testing": "TESTING",
    "Verification": "VERIFICATION",
}


def marker_for_stage(stage: str) -> str:
    try:
        return _MARKER_FOR_STAGE[stage]
    except KeyError:
        raise PdlcError(f"no evidence marker for stage: {stage}") from None


# The one fixed forward path through the lifecycle; used to compute where an
# approval or a stage's completion should hand off to next.
_NEXT_STAGE = {
    "Product": "UI",
    "UI": "Tasks",
    "Tasks": "Technical Plan",
    "Technical Plan": "Implementation",
    "Implementation": "Testing",
    "Testing": "Verification",
    "Verification": "Complete",
}

STAGES = tuple(_NEXT_STAGE)
SKIPPABLE_STAGES = STAGES[1:]


def next_stage(stage: str) -> str:
    try:
        return _NEXT_STAGE[stage]
    except KeyError:
        raise PdlcError(f"no next PDLC stage after: {stage}") from None


def state_after_skip(stage: str) -> tuple[str, str]:
    """Returns the state reached after one declared skip.

    Verification remains a human completion boundary even when its work was
    pre-declared as skipped.
    """
    if stage == "Verification":
        return "Verification", "Approval Required"
    return next_stage(stage), "Pending"


# Routing table

# Maps (Status, Gate State) to (action, autonomous, reason) as pure logic so
# both the mutating pdlc next and read-only pdlc inspect apply the
# exact same routing policy.
# *.Approval Required and *.Decision Required always stop for a human
# regardless of stage.
def action_for(status: str, gate: str) -> tuple[str, bool, str]:
    if gate == "Decision Required":
        return "human-decision", False, "a reviewer raised a blocking decision that only the driver can resolve"
    if gate == "CI Pending":
        return "pdlc-post-ci", True, "the implementation review passed; the shared PR's CI outcome must be recorded"
    if status == "Product" and gate in ("Pending", "Changes Required", "Stale"):
        return "pdlc-write", False, "product artifact is due, and only a human may author it"
    if gate == "Review Required" and status in STAGES:
        return "pdlc-review", True, "review is due"
    if status in ("UI", "Tasks") and gate in ("Pending", "Changes Required", "Stale"):
        return "pdlc-tasks", True, "UI or task artifact is due"
    if status == "Technical Plan" and gate in ("Pending", "Changes Required", "Stale"):
        return "pdlc-plan", True, "technical plan is due"
    if status == "Implementation" and gate in ("Pending", "Changes Required", "Stale"):
        return "pdlc-implement", True, "next eligible delivery task is due"
    if status == "Testing" and gate in ("Pending", "Changes Required", "Stale"):
        return "pdlc-test", True, "acceptance coverage is due"
    if status == "Verification" and gate in ("Pending", "Changes Required", "Stale"):
        return "pdlc-verify", True, "verification is due"
    if gate == "Approval Required":
        return "human-approval", False, "explicit human approval is required"
    if status == "Complete":
        return "none", False, "complete"
    return "blocked", False, "missing or unsupported work item state"


def state_notation(status: str, gate: str) -> str:
    return f"{status.replace(' ', '')}.{gate.replace(' ', '')}"


# What the caller should expect immediately after the dispatched action
# succeeds — not the eventual next stage. Product is the exception: its
# review happens in pdlc-write before publication, so it lands at Approval
# Required.
def next_status_for(status: str, gate: str) -> str:
    if status == "Product" and gate in ("Pending", "Changes Required", "Stale"):
        return state_notation("Product", "Approval Required")

    if gate in ("Pending", "Changes Required", "Stale"):
        return state_notation(status, "Review Required")
    if gate == "Review Required":
        return state_notation(status, "CI Pending" if status == "Implementation" else "Approval Required")
    if gate == "CI Pending":
        return state_notation(status, "Approval Required")
    if gate == "Approval Required":
        return state_notation(status, "Approved")
    return state_notation(status, gate)


# Local files

def require_file(label: str, path: str | os.PathLike | None) -> Path:
    """Separates "you forgot the argument" from "that path isn't there", so a
    typo in a file path reports the path instead of a bare usage line."""
    if not path:
        raise PdlcError(f"{label} is required")
    file_path = Path(path)
    if not file_path.exists():
        raise PdlcError(f"{label} does not exist: {path}")
    if not file_path.is_file():
        raise PdlcError(f"{label} is not a regular file: {path}")
    if file_path.stat().st_size == 0:
        raise PdlcError(f"{label} is empty: {path}")
    return file_path


def evidence_source(label: str, given: str) -> tuple[Path, bool]:
    """Evidence bodies arrive either as a path or as `-` for stdin, so short
    evidence can go inline without a temp file the caller has to create.
    Returns (path, is_temporary) — the caller unlinks the path itself when
    is_temporary is True."""
    if given == "-":
        content = sys.stdin.read()
        if not content:
            raise PdlcError(f"{label} on stdin is empty")
        descriptor, name = tempfile.mkstemp()
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
        return Path(name), True

    return require_file(label, given), False


def unmarked_evidence_source(label: str, given: str) -> tuple[Path, bool]:
    path, is_temporary = evidence_source(label, given)
    with path.open() as handle:
        first_line = handle.readline()
    if first_line.startswith("PDLC-"):
        if is_temporary:
            path.unlink(missing_ok=True)
        raise PdlcError("evidence already starts with a marker; write the body only")
    return path, is_temporary


def read_body_source(text_or_file: str, *, label: str = "body") -> str:
    """Resolve a comment/evidence body given as a literal string, a path to a
    file holding it, or `-` for stdin, to the body text.

    A multi-line value is a literal body, never a path. The filesystem probe
    on a single-line value is defensive: `Path.is_file()` on an over-length
    name raises ENAMETOOLONG on macOS rather than returning False, so any such
    error is caught and the value is taken as a literal body."""
    if text_or_file == "-":
        content = sys.stdin.read()
        if not content:
            raise PdlcError(f"{label} on stdin is empty")
        return content
    if "\n" not in text_or_file:
        try:
            candidate = Path(text_or_file)
            if candidate.is_file():
                return candidate.read_text()
        except OSError:
            pass
    return text_or_file


def load_json_array(label: str, path: Path, *, allow_empty: bool = True) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise PdlcError(f"{label} is not valid JSON: {error}") from None
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "non-empty " if not allow_empty else ""
        raise PdlcError(f"{label} must be a {qualifier}JSON array: {path}")
    if not all(isinstance(entry, dict) for entry in value):
        raise PdlcError(f"every {label} entry must be a JSON object: {path}")
    return value


def duplicates(values: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [value for value, count in counts.items() if count > 1]
