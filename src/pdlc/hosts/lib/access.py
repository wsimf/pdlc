"""Shared shape for the read-only CLI access probes `pdlc doctor` runs against a
backend's host CLI (`gh`, `az`). Each backend's `access.py` fills one report."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

Version = tuple[int, ...]


@dataclass
class AccessReport:
    """`facts` are displayed as-is; `warnings` and `errors` join doctor's own
    lists, so an error fails the command and a warning does not."""

    facts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_version(text: str) -> Version | None:
    """The first dotted number in `text` (`gh version 2.100.0 (...)` -> (2, 100, 0))."""
    match = re.search(r"\d+(?:\.\d+)+", text)
    return tuple(int(part) for part in match.group(0).split(".")) if match else None


def format_version(version: Version) -> str:
    return ".".join(str(part) for part in version)


def check_version(report: AccessReport, name: str, raw: str, minimum: Version) -> None:
    """Displays `name`'s version against `minimum` and warns when it is older or unparseable."""
    version = parse_version(raw)
    required = format_version(minimum)
    if version is None:
        report.facts.append(f"{name} version: {raw.strip() or '(unknown)'} (min {required})")
        report.warnings.append(f"could not parse {name} version {raw.strip()!r}; pdlc is tested with {required}+")
        return
    report.facts.append(f"{name} version: {format_version(version)} (min {required})")
    if version < minimum:
        report.warnings.append(f"{name} {format_version(version)} is older than the minimum {required}; upgrade it")
