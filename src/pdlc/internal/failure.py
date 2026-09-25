"""Report a command failure to the agent that ran it, with an exit code and
recovery steps it can act on.

A non-transient failure keeps the one-line `pdlc: <error>` and exit 1. A
transient one exits 75 when nothing this run wrote is at risk (re-running is
safe) and 76 when a write may have partly landed, in which case the command's
registered `Recovery` says how to tell whether it did. Both start with
`pdlc: transient:` so a caller matching on text still sees the failure is
recoverable. `docs/mutation-recovery.md` is the source for each command's
`Recovery`.
"""

from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass

from pdlc.domain.lifecycle import PdlcError, TransientError
from pdlc.hosts.lib import process

EXIT_FAILURE = 1
EXIT_RETRY = 75
EXIT_RECOVER = 76

# Repeats of the same transient failure an agent should absorb before it stops.
AGENT_RETRIES = 3


@dataclass(frozen=True)
class Recovery:
    """How to tell whether a mutating command's writes landed.

    `check` is the read-only command that shows it, `landed` what that output
    reads when the write landed. `then` replaces the default "it landed.
    Continue." and `otherwise` the default re-run step; either may name the
    exact re-run line as `{rerun}`. `rerun` is False for a command a re-run
    could corrupt: the default otherwise-step then stops and reports instead.
    `note` carries a command-specific caveat, e.g. a duplicate comment a
    re-run leaves behind."""

    check: str
    landed: str
    rerun: bool = True
    then: str | None = None
    otherwise: str | None = None
    note: str | None = None


_recovery: Recovery | None = None
_invocation: str | None = None


def reset() -> None:
    global _recovery, _invocation
    _recovery = None
    _invocation = None


def set_invocation(arguments: list[str]) -> None:
    """Record this run's argv so a recovery can name the exact re-run line."""
    global _invocation
    _invocation = "pdlc " + shlex.join(arguments)


def set_recovery(recovery: Recovery) -> None:
    """Register how to check this command's writes; call before the first one."""
    global _recovery
    _recovery = recovery


def _rerun_line() -> str:
    line = _invocation or "the same pdlc command with the same arguments"
    if _invocation and " - " in f" {_invocation} ":
        line += " (supply the same stdin input again)"
    return line


def report_failure(error: PdlcError, *, rerun_safe: bool = False) -> int:
    """Print `error` for an agent and return the exit code: 1 when it is not
    transient, 75 when re-running is safe (nothing was written, or the caller
    knows its writes are idempotent), 76 when a write may have landed."""
    if not isinstance(error, TransientError):
        print(f"pdlc: {error}", file=sys.stderr)
        return EXIT_FAILURE

    attempts = f" ({error.attempts} attempts)" if error.attempts > 1 else ""
    print(f"pdlc: transient: {error}{attempts}", file=sys.stderr)
    if not process.write_started():
        print(f"pdlc: nothing was changed. Wait a minute, then re-run: {_rerun_line()}", file=sys.stderr)
        return EXIT_RETRY
    if rerun_safe:
        print(f"pdlc: re-running this command is safe. Wait a minute, then re-run: {_rerun_line()}", file=sys.stderr)
        return EXIT_RETRY

    recovery = _recovery
    rerun = _rerun_line()
    lines = ["pdlc: this command may have partly applied, so it was not retried.", "To recover:"]
    if recovery is None:
        lines += [
            "  1. Inspect the work item this command targets.",
            "  2. If the change it makes is already there, it landed. Continue.",
            f"  3. Otherwise re-run: {rerun}",
        ]
    else:
        then = recovery.then or "it landed. Continue."
        otherwise = recovery.otherwise or (
            "re-run: {rerun}" if recovery.rerun else "do not re-run it; stop and report this output to the driver."
        )
        lines += [
            f"  1. Run `{recovery.check}`.",
            f"  2. If {recovery.landed}, {then.replace("{rerun}", rerun)}",
            f"  3. Otherwise {otherwise.replace("{rerun}", rerun)}",
        ]
    lines.append(f"  4. If the same failure repeats {AGENT_RETRIES} times, stop and report it.")
    if recovery is not None and recovery.note:
        lines.append(f"Note: {recovery.note}")
    print("\n".join(lines), file=sys.stderr)
    return EXIT_RECOVER
