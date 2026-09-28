"""Bounded CLI transport shared by provider adapters."""

from __future__ import annotations

import errno
import json
import locale
import os
import random
import shutil
import subprocess
import threading
import time
from collections.abc import Sequence
from typing import Any

from pdlc.domain.lifecycle import PdlcError, TransientError
from pdlc.internal.trace import command_label, console_debug, record_external_call

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


# Transient failures whose request never reached the host, or that the host
# rejected before acting on it: retrying these cannot duplicate a write, so they
# are retried even for a call that is not idempotent. Matched case-insensitively
# against the child's error output.
_NOT_SENT = (
    "could not resolve host",
    "no such host",
    "name or service not known",
    "nodename nor servname",
    "temporary failure in name resolution",
    "getaddrinfo",
    "connection refused",
    "network is unreachable",
    "secondary rate limit",
    "was submitted too quickly",
    "http 429",
    "tf400733",
    "request was blocked",
)

# Transient failures after which the request may or may not have been acted
# on: safe to retry only for an idempotent call.
_MAYBE_SENT = (
    "connection reset",
    "i/o timeout",
    "tls handshake timeout",
    "unexpected eof",
    "\": eof",
    "goaway",
    "http 502",
    "http 503",
    "http 504",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "something went wrong while executing your query",
    "connection aborted",
    "max retries exceeded",
    "httpsconnectionpool",
    "remotedisconnected",
    "readtimeout",
    "wsl/service",
    "utilbindvsockanyport",
    "catastrophic failure",
    "e_unexpected",
    "the i/o operation has been aborted",
)

# `az` reports missing credentials when concurrent `az` processes race on its
# shared token cache, and a re-run then succeeds. The lookup is local, so no
# request was sent: retry it even for a write, then stop as a login failure
# rather than a transient one, since it may really be a missing login.
_CREDENTIAL = ("before you can run azure devops commands",)
_CREDENTIAL_HINT = "run `az login` or `az devops login`, or set AZURE_DEVOPS_EXT_PAT"

# OS errors WSL raises transiently when it cannot start a Windows or Linux
# child. The child never ran, so nothing was sent.
_TRANSIENT_OS_ERRORS = {errno.EIO, errno.ENOEXEC, errno.EAGAIN}

ATTEMPTS = 3
_BACKOFF_SECONDS = (1.0, 2.0)
_RATE_LIMIT_BACKOFF_SECONDS = (5.0, 15.0)
_CREDENTIAL_BACKOFF_SECONDS = (2.0, 4.0)

# Set once this run starts a write, idempotent or not, because a timed-out
# write may still have landed and a command's later writes may not. The CLI boundary reads it to decide whether a
# transient failure leaves the command safe to re-run (see `pdlc.internal.failure`).
_write_lock = threading.Lock()
_write_started = False


def reset_run_state() -> None:
    """Forget any write started by a previous CLI invocation."""
    global _write_started
    with _write_lock:
        _write_started = False


def write_started() -> bool:
    """Whether this run started a host call that writes."""
    return _write_started


def _mark_write(value: bool) -> None:
    global _write_started
    with _write_lock:
        _write_started = value


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


# Output that names a Git conflict is never transient, even when a commit
# subject quoted in it happens to contain a transient pattern.
_HARD = ("conflict", "could not apply")


def _classify(message: str) -> str | None:
    """'not-sent', 'maybe-sent', 'credential', or None for a failure that is
    not transient."""
    lowered = message.lower()
    if any(pattern in lowered for pattern in _HARD):
        return None
    if any(pattern in lowered for pattern in _CREDENTIAL):
        return "credential"
    if any(pattern in lowered for pattern in _NOT_SENT):
        return "not-sent"
    if any(pattern in lowered for pattern in _MAYBE_SENT):
        return "maybe-sent"
    return None


def _attempt(executable: str, args: Sequence[str], input: str | None, timeout: float) -> tuple[str | None, str, str | None]:
    """Run the child once: (stdout, error message, transient kind). stdout is
    None on failure; kind is None when the failure is not transient."""
    started = time.monotonic()
    label = command_label(args)
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
    except subprocess.TimeoutExpired:
        console_debug(f"{label} timed out after {time.monotonic() - started:.1f}s")
        return None, f"{args[0]} timed out after {timeout:g}s", "maybe-sent"
    except OSError as error:
        console_debug(f"{label} could not start after {time.monotonic() - started:.1f}s: {error}")
        kind = "not-sent" if error.errno in _TRANSIENT_OS_ERRORS else None
        return None, f"could not run {args[0]}: {error}", kind
    console_debug(f"{label} exited {result.returncode} after {time.monotonic() - started:.1f}s")
    if result.returncode:
        message = _decode(result.stderr).strip() or f"{args[0]} failed (exit {result.returncode})"
        return None, message, _classify(message)
    return _decode(result.stdout), "", None


def run_process(
    args: Sequence[str],
    *,
    input: str | None = None,
    timeout: float = 120,
    idempotent: bool = False,
    writes: bool | None = None,
    single_request: bool = True,
) -> str:
    """Run one host CLI call and return its decoded stdout.

    `idempotent` says whether running the call twice leaves the same result as
    running it once (a read, or a full replacement). `writes` says whether it
    changes anything at all; it defaults to `not idempotent`, so only a caller
    that knows a call is an idempotent write needs to pass it. A write marks
    this run as having started one before it runs, which is what tells the CLI
    boundary a failure may have left the command half-applied.

    A transient failure is retried when the call is idempotent, or when the
    request provably never reached the host; otherwise it is raised at once as
    `TransientError`, since a retry could duplicate a write. A call that makes
    several requests (`single_request=False`, e.g. a stack submit) cannot prove
    none of them landed, so its failures always count as maybe-sent.

    A missing-credentials failure from `az` is retried the same way as one that
    never reached the host, but if it persists it is raised as a plain
    `PdlcError` with a login hint, not as `TransientError`.
    """
    record_external_call(args[0], args)
    # Resolve PATHEXT launchers such as az.cmd instead of passing a bare name.
    executable = shutil.which(args[0])
    if executable is None:
        raise PdlcError(f"required command not found: {args[0]}")
    if writes is None:
        writes = not idempotent
    wrote_before = _write_started
    if writes:
        _mark_write(True)
    for attempt in range(1, ATTEMPTS + 1):
        if attempt > 1:
            console_debug(f"retrying {command_label(args)} (attempt {attempt}/{ATTEMPTS})")
        output, message, kind = _attempt(executable, args, input, timeout)
        if output is not None:
            if writes:
                _mark_write(True)
            return output
        if kind is None:
            raise PdlcError(message)
        if kind == "credential" and (attempt == ATTEMPTS or not single_request):
            # A hard stop, not a transient one. A multi-request call may have
            # sent earlier requests, so it is not retried and keeps its write
            # mark; otherwise no attempt reached the host after `wrote_before`.
            if writes and not wrote_before and single_request:
                _mark_write(False)
            raise PdlcError(f"{message}\n{_CREDENTIAL_HINT}")
        if kind == "not-sent" and not single_request:
            kind = "maybe-sent"
        if kind == "maybe-sent" and not idempotent:
            raise TransientError(message, attempts=attempt)
        if kind == "maybe-sent":
            # This call may have landed, so the run keeps its write mark even
            # if a later attempt fails before sending.
            wrote_before = wrote_before or writes
        if attempt == ATTEMPTS:
            if writes and not wrote_before:
                # Every attempt failed before reaching the host, so this call
                # wrote nothing.
                _mark_write(False)
            raise TransientError(message, attempts=attempt)
        lowered = message.lower()
        if kind == "credential":
            delays = _CREDENTIAL_BACKOFF_SECONDS
        elif "rate limit" in lowered or "too quickly" in lowered:
            delays = _RATE_LIMIT_BACKOFF_SECONDS
        else:
            delays = _BACKOFF_SECONDS
        delay = delays[min(attempt - 1, len(delays) - 1)]
        record_external_call(args[0], ["retry", str(attempt), message.splitlines()[0] if message else ""])
        _sleep(delay + random.uniform(0, delay / 2))
    raise AssertionError("unreachable")


def parse_json(output: str, command: str) -> Any:
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise PdlcError(f"{command} returned invalid JSON: {error.msg}") from error
