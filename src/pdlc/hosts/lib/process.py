"""Bounded CLI transport shared by provider adapters."""

from __future__ import annotations

import json
import locale
import os
import shutil
import subprocess
from collections.abc import Sequence
from typing import Any

from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.trace import record_external_call

# A child CLI whose stdout is a pipe encodes text with the ambient locale, so a
# non-UTF-8 locale makes `az` write an em dash as the lone byte 0x97. `LC_ALL`
# forces a POSIX child onto UTF-8 and, unlike PYTHONUTF8/PYTHONIOENCODING, is not
# dropped by `az`'s isolated-mode (`python -I`) launcher. Windows ignores it, so
# the decode below is the real safety net there. `gh` (Go) ignores all three.
_UTF8_ENV = {"LC_ALL": "C.UTF-8", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def _decode(raw: bytes) -> str:
    # Decode order: UTF-8 first (the correct answer whenever the child
    # cooperated), then the host's ANSI/locale code page, then Windows-1252
    # explicitly. The Windows `az` build always emits its ANSI code page, so
    # decoding the response with that same code page is an exact inverse, not a
    # lossy guess.
    seen: set[str] = set()
    for name in ("utf-8", locale.getpreferredencoding(False), "cp1252"):
        key = (name or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            text = raw.decode(name)
        except (UnicodeDecodeError, LookupError):
            continue
        return text.replace("\r\n", "\n").replace("\r", "\n")
    # Undefined code-page bytes only: keep the response usable rather than abort.
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def run_process(args: Sequence[str], *, input: str | None = None, timeout: float = 120) -> str:
    record_external_call(args[0], args)
    # Resolve PATHEXT launchers such as az.cmd instead of passing a bare name.
    executable = shutil.which(args[0])
    if executable is None:
        raise PdlcError(f"required command not found: {args[0]}")
    try:
        # Capture bytes, not text: `subprocess`'s text mode decodes on a reader
        # thread whose UnicodeDecodeError escapes as an unhandled thread crash
        # (and a None stdout) on Windows. Decoding here keeps it on this thread.
        result = subprocess.run(
            [executable, *args[1:]],
            input=input.encode("utf-8") if input is not None else None,
            capture_output=True, timeout=timeout, check=False,
            env={**os.environ, **_UTF8_ENV},
        )
    except subprocess.TimeoutExpired as error:
        raise PdlcError(f"{args[0]} timed out after {timeout:g}s; inspect remote state before retrying a write") from error
    except OSError as error:
        raise PdlcError(f"could not run {args[0]}: {error}") from error
    if result.returncode:
        raise PdlcError(_decode(result.stderr).strip() or f"{args[0]} failed (exit {result.returncode})")
    return _decode(result.stdout)


def parse_json(output: str, command: str) -> Any:
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise PdlcError(f"{command} returned invalid JSON: {error.msg}") from error
