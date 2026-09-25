# Transient Error Resilience — Plan

Status: proposed.

## Summary

Make `pdlc` absorb the transient failures agents hit in practice (network timeouts, dropped connections, GitHub 5xx and secondary rate limits, WSL process errors) instead of ending the autonomous loop. Retry automatically where a retry cannot change the outcome. Where it can, stop with a distinct exit code and print recovery steps the agent can carry out: which `pdlc inspect` view to read, what "it landed" looks like, and the exact command to re-run.

## Problem

Every `gh`/`az` call goes through `run_process` (`src/pdlc/hosts/lib/process.py`). Any failure there becomes a plain `PdlcError`, and every command prints `pdlc: <error>` and exits 1. A timeout, a connection reset, and a malformed record all look the same to the caller.

The `pdlc-loop` skill treats any controller failure as a hard stop ("never retry around it"), and the handling-agent prompt says the same for skills. So one network blip ends an autonomous run, and a human has to restart it even though nothing was wrong with the record.

Retrying blindly is not the answer either. Most `post` commands make several writes in sequence (evidence comment, then state change), and some create things (Issues, comments). A retry after a partial write can leave duplicate evidence, a duplicate Issue, or a record whose evidence and state disagree. `docs/mutation-recovery.md` lists every write sequence and what a partial failure leaves behind.

## Goals

- Tell transient failures apart from real ones, at the one transport seam.
- Retry reads, and writes that land in the same final state no matter how often they run, inside the CLI with a bounded backoff.
- When a write may have partly applied, never retry it silently: stop and print recovery steps the agent can carry out.
- Keep the autonomous loop running across transient failures without weakening the hard stop for real ones.
- One exit code and one message shape for every command, so skills need a single rule.

## Non-goals

- Making every create-style write idempotent in this change. The recovery steps make that optional; see Follow-ups.
- Retrying authentication, configuration, validation, or conflict failures. Those stay hard stops.
- Changing any lifecycle rule, gate, or evidence contract.

## Design

### 1. Classify transient failures in `run_process`

Add `TransientError(PdlcError)` in `pdlc.domain.lifecycle`. `run_process` raises it when:

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

### 2. Retry only where a retry is safe

`run_process` takes an `idempotent: bool = False` parameter. When it is true and the call raises `TransientError`, it retries up to 3 attempts in total, with 1s/2s/4s backoff plus jitter, and records each retry in the debug trace. The final failure is re-raised as `TransientError`.

`idempotent=True` is set at the call site, never inferred:

| Safe to retry | Why |
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

Never retried automatically: `gh issue create`, `gh issue comment`, `gh project item-add`, GraphQL mutations that add a sub-issue, `az boards work-item create`, comment creation on Azure, and every `gh stack` write (`rebase`, `sync`, `submit`, `link`, `add`, `init`). A retry there can duplicate an Issue or a comment, or run a rebase against a half-rewritten stack.

### 3. Track whether this run has written anything

`run_process` sets a per-run flag the moment a non-idempotent call *starts*, not when it succeeds, because a timed-out write may still have landed. `cli._reset_runtime` clears it between invocations, as it already does for cached hosts.

This splits every non-retryable failure into two cases:

- **Nothing written yet.** The command failed during its reads or validation. Re-running the exact command is safe. Most timeouts fall here, since commands read before they write.
- **A write may have landed.** The record may be partly updated. The command's recovery steps apply.

### 4. Each mutating command states how to check its own result

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
    """Print `error` for an agent and return the exit code: 75 for a
    transient failure, 1 otherwise."""
```

Every command's `except PdlcError` block (about 35 sites today, each printing and returning 1) calls it instead, so the exit code and wording cannot drift between commands. `docs/mutation-recovery.md` is the source for each command's `check`/`landed`/`note`. A test asserts every mutating command supplies a `Recovery`.

### 5. Output contract

Transient failures exit with **75** (`EX_TEMPFAIL`). All other failures keep exit code 1 and their current message.

The first line always starts with `pdlc: transient:`, so a caller can match on text alone.

Before any write:

```
pdlc: transient: gh timed out after 120s
pdlc: nothing was changed. Re-run: pdlc post review 42 approval-required review.md
```

After a write may have landed:

```
pdlc: transient: connection reset by peer
pdlc: this command may have partly applied to work item 42.
To recover:
  1. Run `pdlc inspect review 42`.
  2. If a PDLC-REVIEW comment for Implementation is the newest marker and gateState is `Approval Required`, it landed. Continue.
  3. Otherwise re-run: pdlc post review 42 approval-required review.md
  4. If the same failure repeats 3 times, stop and report it.
```

Keep the evidence and scratch files a command was given until it succeeds; the skills already say this, and recovery depends on it.

### 6. Keep the loop alive

- **Inside the CLI.** `pdlc next loop` is a read path. When a poll raises `TransientError`, it logs the failure to stderr and backs off exactly as it does for "no work ready", counting against the same `max_attempts`. If every attempt fails transiently, it exits 75 with "re-run `pdlc next loop`". `next` can self-heal a record (a comment plus a state change); a heal that fails part-way is re-applied by the next poll, since the record is still in the healable state.
- **`pdlc post ci --wait`** treats a transient read failure as "still pending" and keeps polling within its existing timeout.
- **In the skills.** `agent/skills/pdlc-loop/SKILL.md` and `references/handling-agent.prompt.md` gain one rule, replacing "never retry": *exit code 75 or a `pdlc: transient:` line means follow the printed recovery steps, up to 3 times, then stop and report; any other failure is still a hard stop.* Stage skills that already say "inspect before retrying" point at that rule and add nothing else. Per-command recovery wording stays in the CLI.

## Testing

- Unit: classification table — sample stderr from `gh`, `az`, and WSL maps to transient or not; auth, 404, 422, and validation errors stay non-transient.
- Unit: `run_process` retries only when `idempotent=True`, respects the attempt cap, and sets the write-started flag before a non-idempotent call runs.
- Unit: `report_failure` returns 75 with the "nothing was changed" form before any write and the recovery form after one.
- Command: every `post_*` command supplies a `Recovery` (table-driven over `src/pdlc/commands/post_*.py`).
- Command: `next loop` backs off on a transient poll failure and succeeds on the next attempt; exits 75 when every attempt fails.
- File backend scenarios: inject a transient failure between each pair of writes in `post write`, `post review`, `post tasks`, and `post complete`, then follow the printed recovery steps and assert the record ends in the same state as an uninterrupted run.

## Rollout

1. Classification, `TransientError`, exit code 75, and `report_failure` with the "nothing was changed" form only. Low risk; immediately keeps the loop alive for read failures.
2. `idempotent=True` at the call sites in the table above.
3. The write-started flag and per-command `Recovery`, driven by `docs/mutation-recovery.md`.
4. `next loop` and `post ci --wait` absorb transient failures; skill rule update.

## Follow-ups

- **Idempotent evidence comments.** Stamp each marker comment with a short content hash (e.g. `<!-- pdlc:key=… -->`). Before posting, a command checks whether the newest comment with that marker has the same key and skips the post if so. That turns most "may have partly applied" cases into "just re-run", and removes the duplicate-comment caveats listed in `docs/mutation-recovery.md`.
- **Idempotent record creation.** `post write` and `post decision` search for an existing Issue with the same slug before creating one, the way deferred decisions already reuse an existing slug, and add an existing Issue to the project if `project item-add` never ran.
- **Write-state-first ordering.** Where a command posts evidence and then moves state, consider which order leaves the more recoverable half-state per command. Deferred until the hash above lands, since it makes the order matter less.
