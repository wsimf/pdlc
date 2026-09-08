"""Bounded CLI transport shared by provider adapters."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from typing import Any

from pdlc.domain.lifecycle import PdlcError


def run_process(args: Sequence[str], *, input: str | None = None, timeout: float = 120) -> str:
    try:
        result = subprocess.run(
            list(args), input=input, capture_output=True, text=True,
            encoding="utf-8", timeout=timeout, check=False,
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
