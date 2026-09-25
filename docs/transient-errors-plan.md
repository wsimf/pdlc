# Transient Error Resilience — Plan

Status: proposed.

## Summary

Make `pdlc` absorb the transient failures agents hit in practice (network timeouts, dropped connections, GitHub 5xx and secondary rate limits, WSL process errors) instead of ending the autonomous loop. Every failure lands in one of three outcomes:

- **Safe to retry**: `pdlc` retries automatically at least once. If the failure persists, it exits **75** and tells the agent to re-run the same command.
- **Not safe to retry**: `pdlc` does not retry. It exits **76** and prints recovery steps the agent can carry out: which `pdlc inspect` view to read, what "it landed" looks like, and the exact command to re-run if it did not.
- **Not transient**: unchanged: exit 1, and the loop stops.

## Problem

Every `gh`/`az` call goes through `run_process` (`src/pdlc/hosts/lib/process.py`). Any failure there becomes a plain `PdlcError`, and every command prints `pdlc: <error>` and exits 1. A timeout, a connection reset, and a malformed record all look the same to the caller.

The `pdlc-loop` skill treats any controller failure as a hard stop ("never retry around it"), and the handling-agent prompt says the same for skills. So one network blip ends an autonomous run, and a human has to restart it even though nothing was wrong with the record.

Retrying blindly is not the answer either. Most `post` commands make several writes in sequence (evidence comment, then state change), and some create things (Issues, comments). A retry after a partial write can leave duplicate evidence, a duplicate Issue, or a record whose evidence and state disagree. `docs/mutation-recovery.md` lists every write sequence and what a partial failure leaves behind.

## Goals

- Tell transient failures apart from real ones, at the one transport seam.
- Whenever a retry is safe, retry automatically inside the CLI, at least once, with a bounded backoff, and hand a persistent failure to the agent as "re-run this command".
- Whenever a retry is not safe, never retry silently: stop and print recovery steps the agent can carry out.
- Keep the autonomous loop running across transient failures without weakening the hard stop for real ones.
- Two exit codes and one message shape for every command, so skills need a single two-branch rule.

## Non-goals

- Making every create-style write idempotent in this change. The recovery steps make that optional; see Follow-ups.
- Retrying authentication, configuration, validation, or conflict failures. Those stay hard stops.
- Changing any lifecycle rule, gate, or evidence contract.

## Design

### 1. Classify transient failures in `run_process`

Add `TransientError(PdlcError)` in `pdlc.domain.lifecycle`, carrying a `retryable` flag (section 3). `run_process` treats a failure as transient when:

- the child times out (`subprocess.TimeoutExpired`);
- starting the child fails with an OS error that WSL produces transiently (`EIO` "Input/output error", `ENOEXEC` "Exec format error", vsock/interop failures);
- the child exits non-zero and its error output matches a known transient pattern.

The patterns live in one module-level tuple so new ones can be added as they show up in logs:

| Source | Patterns |
| --- | --- |
| Network | `connection reset`, `connection refused`, `i/o timeout`, `TLS handshake timeout`, `could not resolve host`, `no such host`, `EOF`, `network is unreachable`, `unexpected EOF` |
| GitHub | `HTTP 502`, `HTTP 503`, `HTTP 504`, `secondary rate limit`, `Something went wrong while executing your query`, `was submitted too quickly` |
| Azure CLI | `Connection aborted`, `Max retries exceeded`, `HTTPSConnectionPool`, `RemoteDisconnected`, `ReadTimeout` |
| WSL | `Wsl/Service`, `UtilBindVsockAnyPort`, `Catastrophic failure`, `E_UNEXPECTED`, `The I/O operation has been aborted` |

Authentication (`HTTP 401`, `gh auth login`), permission (`HTTP 403` without "rate limit"), `HTTP 404`, `HTTP 422`, and GraphQL validation errors are never transient.

### 2. Decide whether a retry is safe

A transient failure is safe to retry when running the call again cannot change the outcome. `run_process` decides this per call from two facts:

1. **Is the call idempotent?** Set at the call site with `idempotent=True`, never inferred.
2. **Could the request have reached the server?** Some failures happen before anything is sent: `could not resolve host`, `no such host`, `connection refused`, `network is unreachable`, and a WSL failure to start the child process (`Exec format error`, vsock/interop errors). A call that failed this way changed nothing, so it is safe to retry even when it is not idempotent. Every other transient failure (a timeout, a reset or dropped connection, a 5xx, `unexpected EOF`) may have landed on the server.

| Call | Failure before sending | Failure after sending |
| --- | --- | --- |
| Idempotent | Safe: retry | Safe: retry |
| Not idempotent | Safe: retry | **Not safe**: no retry |

Idempotent calls (`idempotent=True`):

| Call | Why |
| --- | --- |
| GraphQL queries (`run_graphql` when the document starts with `query`) | Read-only. |
| `gh api` GET, `gh issue view`, `gh pr view`, `gh stack view`, `gh api user`, `gh extension list` | Read-only. |
| `az boards work-item show`, `az boards query`, `az account show`, `az devops invoke` with GET | Read-only. |
| `gh issue edit --body-file` / `--title` (full replacement) | Same final state on every run. |
| `gh issue close`, `gh issue reopen`, `gh pr ready` | Same final state on every run. |
| Project single-select and text field updates (`set_gate`, `set_slug`, `set_skipped_states`) | Same final state on every run; `set_state` already re-reads and reconciles once. |
| `gh api --method PATCH` on a comment (`edit_comment`) | Full replacement. |
| `gh api --method DELETE` on a comment | A second delete returns 404, which the call site treats as done. |
| `az boards work-item update` | Full field replacement. |

Not idempotent: `gh issue create`, `gh issue comment`, `gh project item-add`, GraphQL mutations that add a sub-issue, `az boards work-item create`, comment creation on Azure, and every `gh stack` write (`rebase`, `sync`, `submit`, `link`, `add`, `init`). Retrying one of these after the request may have been sent can duplicate an Issue or a comment, or run a rebase against a half-rewritten stack.

### 3. Retry automatically when it is safe

When a call fails with a transient error and the table above says it is safe, `run_process` retries it: at least one retry, 3 attempts in total by default, with 1s/2s/4s backoff plus jitter, each attempt recorded in the debug trace. A secondary-rate-limit response waits for GitHub's `Retry-After` when it gives one, capped at 60s.

If the call succeeds on a retry, the command carries on as if nothing happened. If every attempt fails, `run_process` raises `TransientError(retryable=True)`.

When the call is not safe to retry, `run_process` raises `TransientError(retryable=False)` straight away, with no retry.

### 4. Track whether this run has written anything

A retryable failure of one call does not make the whole *command* safe to re-run: an earlier write in the same command may already have landed. So `run_process` also sets a per-run flag the moment a non-idempotent call *starts*, not when it succeeds, because a timed-out write may still have landed. `cli._reset_runtime` clears it between invocations, as it already does for cached hosts.

The flag and the error together decide the outcome of the command:

| Error | Earlier non-idempotent write started? | Outcome |
| --- | --- | --- |
| `retryable=True` (retries exhausted) | No | Exit **75**: re-run the same command. |
| `retryable=True` (retries exhausted) | Yes | Exit **76**: follow the recovery steps. |
| `retryable=False` | Either | Exit **76**: follow the recovery steps. |
| Not transient | Either | Exit 1: unchanged. |

A read-only command never sets the flag, so its transient failures always end at 75.

### 5. Each mutating command states how to check its own result

The transport knows only `gh issue comment 42 …`. The command knows the work item, the evidence it was landing, and which inspect view proves it. So each `post_*` command (and `checkout`, `continue`) builds a `Recovery` value before its first write:

```python
@dataclass(frozen=True)
class Recovery:
    check: str            # e.g. "pdlc inspect review 42"
    landed: str           # e.g. "a PDLC-REVIEW comment for Implementation is the newest marker and gateState is Approval Required"
    rerun: str            # the exact command line, reconstructed from argv
    note: str | None = None  # command-specific caveat, e.g. a duplicate-comment warning
```

A shared helper in `pdlc.internal.reporting` renders the error:

```python
def report_failure(error: PdlcError, recovery: Recovery | None) -> int:
    """Print `error` for an agent and return the exit code: 75 when re-running
    the command is safe, 76 when the agent must check before re-running, 1 when
    the failure is not transient."""
```

Every command's `except PdlcError` block (about 35 sites today, each printing and returning 1) calls it instead, so the exit codes and wording cannot drift between commands. `docs/mutation-recovery.md` is the source for each command's `check`/`landed`/`note`. A test asserts every mutating command supplies a `Recovery`.

### 6. Output contract

| Exit | Meaning | First line |
| --- | --- | --- |
| 0 | Success, including a success after automatic retries. | — |
| 1 | Not transient. Unchanged. | `pdlc: <error>` |
| **75** | Transient; the CLI retried and it persisted; nothing this command wrote is at risk. Re-running the same command is safe. | `pdlc: transient: <error>` |
| **76** | Transient; a write may have partly applied. Check before re-running. | `pdlc: transient: <error>` |

75 is `EX_TEMPFAIL`. 76 is a `pdlc`-specific code in the same range with no conventional meaning that could clash. Both start with `pdlc: transient:`, so a caller that matches on text alone still knows the failure is recoverable.

Exit 75, safe to retry but it persisted:

```
pdlc: transient: gh timed out after 120s (3 attempts)
pdlc: nothing was changed. Wait a minute, then re-run: pdlc post review 42 approval-required review.md
```

Exit 76, not safe to retry:

```
pdlc: transient: connection reset by peer while posting a comment
pdlc: this command may have partly applied to work item 42, so it was not retried.
To recover:
  1. Run `pdlc inspect review 42`.
  2. If a PDLC-REVIEW comment for Implementation is the newest marker and gateState is `Approval Required`, it landed. Continue.
  3. Otherwise re-run: pdlc post review 42 approval-required review.md
  4. If the same failure repeats 3 times, stop and report it.
```

When a command has no safe recovery (the hazards listed at the end of `docs/mutation-recovery.md`), its `Recovery` says so, and step 3 becomes "stop and report this output to the driver" instead of a re-run.

Keep the evidence and scratch files a command was given until it succeeds; the skills already say this, and recovery depends on it.

### 7. Keep the loop alive

- **Inside the CLI.** `pdlc next loop` is a read path. Its reads already get automatic retries. When a poll still fails with exit-75 conditions, it logs the failure to stderr and backs off exactly as it does for "no work ready", counting against the same `max_attempts`. If every attempt fails transiently, it exits 75 with "re-run `pdlc next loop`". `next` can self-heal a record (a comment plus a state change); a heal that fails part-way is re-applied by the next poll, since the record is still in the healable state, so `next` never needs 76.
- **`pdlc post ci --wait`** treats a transient read failure as "still pending" and keeps polling within its existing timeout.
- **In the skills.** `agent/skills/pdlc-loop/SKILL.md` and `references/handling-agent.prompt.md` gain one rule, replacing "never retry": *exit 75: wait a minute and re-run the same command; exit 76: follow the printed recovery steps; either one up to 3 times, then stop and report. Any other failure is still a hard stop.* Stage skills that already say "inspect before retrying" point at that rule and add nothing else. Per-command recovery wording stays in the CLI.

## Testing

- Unit: classification table — sample stderr from `gh`, `az`, and WSL maps to transient or not; auth, 404, 422, and validation errors stay non-transient.
- Unit: `run_process` retries an idempotent call, and a non-idempotent call that failed before sending, at least once and up to the attempt cap; never retries a non-idempotent call that failed after sending; and sets the write-started flag before a non-idempotent call runs.
- Unit: a call that succeeds on a retry leaves the command's output and exit code unchanged.
- Unit: `report_failure` returns 75 for an exhausted retryable failure before any write, and 76 with the recovery form for a non-retryable failure or any failure after a write.
- Command: every `post_*` command supplies a `Recovery` (table-driven over `src/pdlc/commands/post_*.py`).
- Command: `next loop` backs off on a transient poll failure and succeeds on the next attempt; exits 75 when every attempt fails, never 76.
- File backend scenarios: inject a transient failure between each pair of writes in `post write`, `post review`, `post tasks`, and `post complete`, then follow the printed exit-75 or exit-76 instructions and assert the record ends in the same state as an uninterrupted run.

## Rollout

1. Classification (including before/after sending), `TransientError`, and automatic retries for idempotent calls. Low risk; most blips never reach the agent.
2. Exit 75 and `report_failure` with the "nothing was changed" form, for read-only commands and for failures before any write.
3. The write-started flag, exit 76, and per-command `Recovery`, driven by `docs/mutation-recovery.md`.
4. `next loop` and `post ci --wait` absorb transient failures; skill rule update.

## Follow-ups

- **Idempotent evidence comments.** Stamp each marker comment with a short content hash (e.g. `<!-- pdlc:key=… -->`). Before posting, a command checks whether the newest comment with that marker has the same key and skips the post if so. That makes the evidence post idempotent, so it joins the auto-retry path and most exit-76 cases become automatic retries, and removes the duplicate-comment caveats listed in `docs/mutation-recovery.md`.
- **Idempotent record creation.** `post write` and `post decision` search for an existing Issue with the same slug before creating one, the way deferred decisions already reuse an existing slug, and add an existing Issue to the project if `project item-add` never ran.
- **Write-state-first ordering.** Where a command posts evidence and then moves state, consider which order leaves the more recoverable half-state per command. Deferred until the hash above lands, since it makes the order matter less.
