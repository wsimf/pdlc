"""Append external CLI invocations to a debug log when tracing is on.

Enabled by ``[debug] enabled = true`` in ``.pdlc/config.toml`` (or
``~/.pdlc/config.toml``); a ``PDLC_DEBUG`` environment variable is honoured too,
so tracing can be turned on before any config file is located.
Every ``az`` / ``gh`` call routes through ``pdlc.hosts.lib.process.run_process``
and every ``git`` call through the ``pdlc.internal`` VCS/worktree helpers, so a
``record_external_call`` at each of those seams captures the full set.

Logging is best-effort: a failure to write the log never breaks the command.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

_LOG_PATH = Path.home() / ".pdlc" / "debug.log"


def _enabled() -> bool:
    if (os.environ.get("PDLC_DEBUG") or "false").lower() in {"true", "1"}:
        return True
    # Reach for the cached config only; loading it here would recurse, since
    # `git_remote_repository` records a call through this seam.
    from pdlc import config

    return config._config is not None and config._config.debug


def record_external_call(tool: str, args: Sequence[str]) -> None:
    """Append one ``[time] - (tool) : full command`` line when tracing is on."""
    if not _enabled():
        return
    line = f"[{datetime.now().isoformat(timespec='seconds')}] - ({tool}) : {shlex.join(args)}\n"
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(line)
    except OSError:
        pass
