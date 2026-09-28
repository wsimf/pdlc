"""File tracing and invocation-only console diagnostics for external calls.

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
import sys
import threading
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

_LOG_PATH = Path.home() / ".pdlc" / "debug.log"
_console_debug = False
_console_lock = threading.Lock()


def set_console_debug(enabled: bool) -> None:
    """Enable console diagnostics for this invocation only."""
    global _console_debug
    _console_debug = enabled


def console_debug(message: str) -> None:
    if not _console_debug:
        return
    with _console_lock:
        print(f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] DEBUG pdlc: {message}", file=sys.stderr, flush=True)


def command_label(args: Sequence[str]) -> str:
    """Show command identity without echoing payloads or credentials."""
    count = 3 if len(args) > 2 and args[0] == "gh" and args[1] == "stack" else 2
    return " ".join(args[:count])


def _enabled() -> bool:
    if (os.environ.get("PDLC_DEBUG") or "false").lower() in {"true", "1"}:
        return True
    # Reach for the cached config only; loading it here would recurse, since
    # `git_remote_repository` records a call through this seam.
    from pdlc import config

    return config._config is not None and config._config.debug


def record_external_call(tool: str, args: Sequence[str]) -> None:
    """Append one ``[time] - (tool) : full command`` line when tracing is on."""
    if args and args[0] != "retry":
        console_debug(f"starting {command_label(args)}")
    if not _enabled():
        return
    line = f"[{datetime.now().isoformat(timespec='seconds')}] - ({tool}) : {shlex.join(args)}\n"
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(line)
    except OSError:
        pass
