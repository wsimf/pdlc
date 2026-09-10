"""Bounded CLI transport shared by provider adapters."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from typing import Any

from pdlc.domain.lifecycle import PdlcError

# When a child CLI's stdout is a pipe (as it is here) it encodes text with the
# ambient locale, so under a non-UTF-8 locale `az` emits an em dash as the lone
# CP-1252 byte 0x97 and our UTF-8 decode fails — after the write has landed.
# `LC_ALL` forces the child onto UTF-8 and, unlike PYTHONUTF8/PYTHONIOENCODING,
# is not discarded by `az`'s isolated-mode (`python -I`) launcher. The PYTHON*
# vars still help the non-isolated wrappers. `gh` (Go) ignores all of them.
_UTF8_ENV = {"LC_ALL": "C.UTF-8", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def run_process(args: Sequence[str], *, input: str | None = None, timeout: float = 120) -> str:
    # Resolve PATHEXT launchers such as az.cmd instead of passing a bare name.
    executable = shutil.which(args[0])
    if executable is None:
        raise PdlcError(f"required command not found: {args[0]}")
    try:
        result = subprocess.run(
            [executable, *args[1:]], input=input, capture_output=True, text=True,
            encoding="utf-8", timeout=timeout, check=False,
            env={**os.environ, **_UTF8_ENV},
        )
    except subprocess.TimeoutExpired as error:
        raise PdlcError(f"{args[0]} timed out after {timeout:g}s; inspect remote state before retrying a write") from error
    except (OSError, UnicodeError) as error:
        raise PdlcError(f"could not run {args[0]}: {error}") from error
    if result.returncode:
        raise PdlcError(result.stderr.strip() or f"{args[0]} failed (exit {result.returncode})")
    return result.stdout


def parse_json(output: str, command: str) -> Any:
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise PdlcError(f"{command} returned invalid JSON: {error.msg}") from error
