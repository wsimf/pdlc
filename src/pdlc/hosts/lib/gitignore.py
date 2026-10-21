"""Read-only Git ignore check for local PDLC files."""

from __future__ import annotations

import subprocess
from pathlib import Path


def pdlc_unignored(root: Path) -> bool:
    """True only when Git confirms `.pdlc/` is not ignored under `root`.

    Reads every ignore source Git uses (repository, info/exclude, global), so
    a global rule counts. A missing Git, a non-repository, or any other Git
    failure returns False so callers never warn on an unknown state.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", ".pdlc/"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 1
