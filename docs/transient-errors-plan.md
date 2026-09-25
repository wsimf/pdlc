# Transient Error Resilience — Plan

Status: implemented. Classification and retries live in `src/pdlc/hosts/lib/process.py`, idempotency allowlists in the GitHub and Azure transports, and exit codes and recovery output in `src/pdlc/internal/failure.py`.

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

Add `TransientError(PdlcError)` in `pdlc.domain.lifecycle`, carrying the number of attempts made. `run_process` in `pdlc.hosts.lib.process` treats a failure as transient when:

- the child times out (`subprocess.TimeoutExpired`);
- starting the child fails with an OS error that WSL produces transiently (`EIO` "Input/output error", `ENOEXEC` "Exec format error", `EAGAIN`);
- the child exits non-zero and its error output matches a known transient pattern.

The patterns live in two module-level tuples, `_NOT_SENT` and `_MAYBE_SENT` (section 2), so new ones can be added as they show up in logs:

| Source | Patterns |
| --- | --- |
| Network | `connection reset`, `connection refused`, `i/o timeout`, `TLS handshake timeout`, `could not resolve host`, `no such host`, `name or service not known`, `temporary failure in name resolution`, `getaddrinfo`, `network is unreachable`, `unexpected EOF` |
| GitHub | `HTTP 502`, `HTTP 503`, `HTTP 504`, `HTTP 429`, `secondary rate limit`, `Something went wrong while executing your query`, `was submitted too quickly` |
| Azure CLI | `Connection aborted`, `Max retries exceeded`, `HTTPSConnectionPool`, `RemoteDisconnected`, `ReadTimeout` |
| WSL | `Wsl/Service`, `UtilBindVsockAnyPort`, `Catastrophic failure`, `E_UNEXPECTED`, `The I/O operation has been aborted` |

Authentication (`HTTP 401`, `gh auth login`), permission (`HTTP 403` without "rate limit"), `HTTP 404`, `HTTP 422`, and GraphQL validation errors are never transient.

### 2. Decide whether a retry is safe

A transient failure is safe to retry when running the call again cannot change the outcome. `run_process` decides this per call from two facts:

1. **Is the call idempotent?** `run_process(..., idempotent=False, writes=None)` defaults to a non-idempotent write. The provider transports classify each call from its argv as `read` (changes nothing), `set` (replaces a value outright, so running it twice equals running it once) or `add` (anything a retry could duplicate), with `gh_call_kind` in `hosts/lib/github/transport.py` and `az_call_kind` in `hosts/lib/azure/transport.py`, so the test fakes that replace `run_gh`/`run_az` need no new parameter. A `read` or `set` call is idempotent; a `set` or `add` call writes; anything unlisted counts as `add`. A `gh api` call is classified by its HTTP method (GET read; PATCH, PUT and DELETE set; POST add) and a GraphQL call by its mutation fields. A `gh stack` call pushes several branches and PRs, so it passes `single_request=False`: none of its failures can prove nothing was sent. The few direct `run_process` callers (doctor's access checks, `git rev-parse`) pass `idempotent=True` themselves.
2. **Could the request have reached the server?** Some failures happen before anything is sent, or are rejected before the host acts: DNS failures, `connection refused`, `network is unreachable`, a secondary rate limit or `HTTP 429`, and a WSL failure to start the child process (`EIO`, `ENOEXEC`, `EAGAIN`). A call that failed this way changed nothing, so it is safe to retry even when it is not idempotent. Every other transient failure (a timeout, a reset or dropped connection, a 5xx, `unexpected EOF`) may have landed on the server. Output that names a Git conflict (`conflict`, `could not apply`) is never transient, even when a quoted commit subject contains one of these patterns.

| Call | Failure before sending | Failure after sending |
| --- | --- | --- |
| Idempotent | Safe: retry | Safe: retry |
| Not idempotent | Safe: retry | **Not safe**: no retry |

Idempotent calls (the allowlists):

| Call | Why |
| --- | --- |
| GraphQL documents that are not a `mutation` | Read-only. |
| GraphQL mutations whose every field is `updateProjectV2ItemFieldValue` | Same final state on every run. |
| `gh api` without a body field or with `--method GET`, `gh issue view`/`list`, `gh pr view`/`list`/`checks`, `gh project view`/`list`/`field-list`/`item-list`, `gh stack view`, `gh extension list`, `gh auth status`, `gh repo view` | Read-only. |
| `az boards work-item show`, `az boards query`, `az account show`, `az devops invoke` with GET or no `--http-method` | Read-only. |
| `gh issue edit --body-file` / `--title` (full replacement) | Same final state on every run. |
| `gh issue close`, `gh issue reopen`, `gh pr ready`, `gh pr edit`, `gh project item-edit` | Same final state on every run. |
| Project single-select and text field updates (`set_gate`, `set_slug`, `set_skipped_states`) | Same final state on every run; `set_state` already re-reads and reconciles once. |
| `gh api --method PATCH` or `PUT` (`edit_comment`) | Full replacement. |
| `gh api --method DELETE` on a comment | A second delete returns 404, which `delete_comment` treats as done. |
| `az boards work-item update`, `az devops invoke` with PATCH or PUT | Full field replacement. |

Not idempotent: `gh issue create`, `gh issue comment`, `gh project item-add`, a `gh api` POST, GraphQL mutations that add a sub-issue, `az boards work-item create`, `az boards work-item relation add`, `az devops invoke` with POST or DELETE (Azure comment creation), and every `gh stack` write (`rebase`, `sync`, `submit`, `link`, `add`, `init`). Retrying one of these after the request may have been sent can duplicate an Issue or a comment, or run a rebase against a half-rewritten stack.

### 3. Retry automatically when it is safe

When a call fails with a transient error and the table above says it is safe, `run_process` retries it: 3 attempts in total, waiting 1s then 2s plus up to 50% jitter, each retry recorded in the debug trace. A rate-limit response (`rate limit`, `submitted too quickly`) waits 5s then 15s instead; `gh` does not pass GitHub's `Retry-After` through its error output, so the wait is fixed.

If the call succeeds on a retry, the command carries on as if nothing happened. If every attempt fails, `run_process` raises `TransientError` with the attempt count.

When the call is not safe to retry, `run_process` raises `TransientError` straight away, with no retry. Wrappers that re-raise a host failure in their own words (`set_state` and `link_subissues` after their reconciliation pass, the pull-request lookups in `code_host`) keep a transient cause transient.

### 4. Track whether this run has written anything

A retryable failure of one call does not make the whole *command* safe to re-run: an earlier write in the same command may already have landed, and a later write may not. So `run_process` also sets a per-run flag the moment any write *starts*, idempotent or not, and not when it succeeds, because a timed-out write may still have landed. When every attempt of a run's first write failed before sending, the flag is cleared again, since nothing was written. `cli._reset_runtime` clears it between invocations, as it already does for cached hosts.

The flag and the error together decide the outcome of the command:

| Error | Write started this run? | Outcome |
| --- | --- | --- |
| Transient | No | Exit **75**: re-run the same command. |
| Transient | Yes | Exit **76**: follow the recovery steps. |
| Not transient | Either | Exit 1: unchanged. |

A read-only command never sets the flag, so its transient failures always end at 75. A write that failed after it may have been sent has set the flag, so it always ends at 76.

### 5. Each mutating command states how to check its own result

The transport knows only `gh issue comment 42 …`. The command knows the work item, the evidence it was landing, and which inspect view proves it. So each `post_*` command (and `checkout`, `continue`) builds a `Recovery` value before its first write:

```python
@dataclass(frozen=True)
class Recovery:
    check: str                     # e.g. "pdlc inspect timeline 42"
    landed: str                    # what `check` shows when the write landed
    rerun: bool = True             # False: the default step 3 stops and reports instead of re-running
    then: str | None = None        # replaces "it landed. Continue."
    otherwise: str | None = None   # replaces the re-run step; `{rerun}` names the re-run line
    note: str | None = None        # command-specific caveat, e.g. a duplicate-comment warning
```

The command registers it with `set_recovery`. The re-run line is the invocation's own argv, which `cli.main` records with `set_invocation`. A shared helper in `pdlc.internal.failure` renders the error:

```python
def report_failure(error: PdlcError, *, rerun_safe: bool = False) -> int:
    """Print `error` for an agent and return the exit code: 75 when re-running
    the command is safe, 76 when the agent must check before re-running, 1 when
    the failure is not transient."""
```

Every command's `except PdlcError` block (48 sites, each printing and returning 1) calls it instead, and `cli.main` catches a `TransientError` a command left uncaught, so the exit codes and wording cannot drift between commands. `next` passes `rerun_safe=True`, since its only writes are heals a re-run re-applies; its 75 then says "re-running this command is safe" rather than "nothing was changed". `docs/mutation-recovery.md` is the source for each command's `check`/`landed`/`note`. A test asserts every mutating command supplies a `Recovery`.

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
pdlc: transient: connection reset by peer
pdlc: this command may have partly applied, so it was not retried.
To recover:
  1. Run `pdlc inspect 42`.
  2. If the gate is Review Required and `pdlc inspect timeline 42` shows this PDLC-IMPLEMENTATION evidence as the newest, it landed. Continue.
  3. Otherwise re-run: pdlc post implement 42 implementation.md
  4. If the same failure repeats 3 times, stop and report it.
Note: A re-run after the evidence landed posts a second PDLC-IMPLEMENTATION comment; mention it in your report.
```

When a command has no safe recovery (the hazards listed at the end of `docs/mutation-recovery.md`), its `Recovery` says so, and step 3 becomes "stop and report this output to the driver" instead of a re-run.

Keep the evidence and scratch files a command was given until it succeeds; the skills already say this, and recovery depends on it.

### 7. Keep the loop alive

- **Inside the CLI.** `pdlc next loop` is a read path. Its reads already get automatic retries. When a poll still fails with exit-75 conditions, it logs the failure to stderr and backs off exactly as it does for "no work ready", counting against the same `max_attempts`. If every attempt fails transiently, it exits 75 with "re-run `pdlc next loop`". `next` can self-heal a record (a comment plus a state change); a heal that fails part-way is re-applied by the next poll, since the record is still in the healable state, so `next` never needs 76.
- **`pdlc post ci --wait`** treats a transient read failure as "still pending" and keeps polling within its existing timeout.
- **In the skills.** `agent/skills/pdlc-loop/SKILL.md` and `agent/skills/pdlc-loop/references/handling-agent.prompt.md` gain one rule, and `pdlc guide contract` states the same, replacing "never retry": *exit 75: wait a minute and re-run the same command; exit 76: follow the printed recovery steps; either one up to 3 times, then stop and report. Any other failure is still a hard stop.* Stage skills add nothing: the handling agent runs them and applies the rule. Per-command recovery wording stays in the CLI.

## Testing

- Unit: classification table — sample stderr from `gh`, `az`, and WSL maps to transient or not; auth, 404, 422, and validation errors stay non-transient.
- Unit: `run_process` retries an idempotent call, and a non-idempotent call that failed before sending, at least once and up to the attempt cap; never retries a non-idempotent call that failed after sending; and sets the write-started flag before any write runs, including an idempotent one.
- Unit: a call that succeeds on a retry leaves the command's output and exit code unchanged.
- Unit: `report_failure` returns 75 for a transient failure before any write, and 76 with the recovery form for any transient failure after a write started.
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
