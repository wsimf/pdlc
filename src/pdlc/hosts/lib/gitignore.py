"""Best-effort Git ignore setup for local PDLC files."""

from __future__ import annotations

import subprocess
from pathlib import Path


def ensure_pdlc_ignored(root: Path) -> None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", ".pdlc/"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 1:
            return

        ignore_file = root / ".gitignore"
        existing = ignore_file.read_bytes() if ignore_file.exists() else b""
        with ignore_file.open("ab") as stream:
            stream.write((b"" if not existing or existing.endswith(b"\n") else b"\n") + b"/.pdlc/\n")
    except OSError:
        pass
