"""Command input files, stdin, and help rendering."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.trace import console_debug


def wants_help(argv: list[str]) -> bool:
    return not argv or any(argument in ("-h", "--help") for argument in argv)


def print_help(doc: str | None) -> None:
    print((doc or "").strip())


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


# stdin arrives as `-` from a heredoc or pipe; the device paths are the same
# stream under a different name and agents reach for them interchangeably, so
# all four resolve to "read stdin" rather than being treated as file paths.
_STDIN_ALIASES = ("-", "/dev/stdin", "/dev/fd/0", "/proc/self/fd/0")


def is_stdin(value: str) -> bool:
    """True when `value` names the stdin stream rather than a file path."""
    return value in _STDIN_ALIASES


def resolve_text(value: str, *, label: str) -> str:
    """Resolve an evidence or comment-body argument to its text.

    Three explicit forms, no path/literal guessing:
      * `text:<body>` — everything after the prefix is the literal body.
      * `-` (or a stdin device path) — read all of stdin.
      * anything else — a path to a UTF-8 file; an unknown path is an error,
        never a silent literal.

    Blank content is refused on every form so a stage can never publish an
    empty body.
    """
    if value.startswith("text:"):
        console_debug(f"reading inline {label}")
        text = value[len("text:"):]
        if not text.strip():
            raise PdlcError(f"{label} is empty")
        return text

    from_stdin = is_stdin(value)
    console_debug(f"reading {label} from {'stdin' if from_stdin else 'file'}")
    try:
        text = sys.stdin.read() if from_stdin else require_file(label, value).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise PdlcError(f"could not read {label}: {error}") from error
    if not text.strip():
        raise PdlcError(f"{label}{' on stdin' if from_stdin else ''} is empty")
    return text


def assert_unmarked(text: str, label: str) -> None:
    """Reject a body that already opens with a `PDLC-` marker line — a sign the
    caller pasted a rendered comment back instead of writing just the body."""
    if text.lstrip().startswith("PDLC-"):
        raise PdlcError(f"{label} already starts with a marker; write the body only")


def load_json_array(label: str, path: Path, *, allow_empty: bool = True) -> list[dict[str, Any]]:
    console_debug(f"loading {label} JSON array")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PdlcError(f"{label} is not valid JSON: {error}") from None
    except (OSError, UnicodeError) as error:
        raise PdlcError(f"could not read {label}: {error}") from error
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "non-empty " if not allow_empty else ""
        raise PdlcError(f"{label} must be a {qualifier}JSON array: {path}")
    if not all(isinstance(entry, dict) for entry in value):
        raise PdlcError(f"every {label} entry must be a JSON object: {path}")
    return value
