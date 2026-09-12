"""Loads the git-ignored live E2E configuration, if present.

Each live suite needs identifiable project details (repository, Project
owner/number for GitHub; organization/project for Azure DevOps) that must
never be committed. Both backends' sections live in the one file, next to
this module, named ``live_config.toml`` — see ``live_config.toml.example``
for its shape. A suite whose table is absent from the file, or for whom the
file itself is missing, skips rather than failing; nothing here raises.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "live_config.toml"


def load_section(name: str) -> dict[str, str] | None:
    """The `[name]` table from `live_config.toml`, or None if the file or
    that table is missing."""
    if not CONFIG_PATH.exists():
        return None
    data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    section = data.get(name)
    return section if isinstance(section, dict) else None
