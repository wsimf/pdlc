---
name: pdlc-loop
description: "Poll the PDLC queue, dispatch the specialist skill the controller names, and keep polling until a human is required. Use when asked to run the PDLC queue, pick up the next item, or continue autonomous PDLC work."
argument-hint: "Optional work item number to prioritise"
disable-model-invocation: true
---

# Run the PDLC queue

This skill decides nothing about the work itself. It asks the controller what is next, hands the returned instruction to the specialist skill named in it, and repeats until a human is required. Routing lives in the controller; the work lives in the specialists — you are the orchestrator.

Read `references/loop-contract.md` for the retry contract, and `pdlc guide contract` before dispatching.

## Required input

None. With no argument the controller scans the whole queue. An work item number prioritises that one record — pass it through verbatim, never infer one from the branch, recent files, or open PRs.

The run is autonomous by default: it keeps polling and dispatching until something needs a human. A driver who wants one action and a report says so ("just the next action", "one pass") — then Step 3 stops after the first.

---

## Step 1: Ask the controller what is next

```bash
pdlc next loop
pdlc next loop WORK_ITEM   # one record
```

Returns a Markdown document: YAML front matter — `id`, `work_item_number`, `title`, `current_status`, `action` — then the record's `# Due Next` section, exactly as `pdlc inspect <work-item>` renders it for the state just routed. That section is the instruction for this pass; `action` only classifies it. `action` is a `pdlc-*` skill name or `pdlc-post-ci` (autonomous), or `human-input` / `human-approval` / `human-decision` / `blocked` (a stop), and always agrees with what `# Due Next` names. A record with nothing to act on — an exhausted no-work scan, a `CI Pending` record whose checks are still running, or a Complete record — carries `action: none` and a short notice instead of a `# Due Next` section, plus an `attempts` count when the scan was exhausted.

The scan dispatches the first autonomous action, or surfaces the first human stop when none is available, and auto-advances past any `Skipped States` stage and self-heals a stray gate before deciding.

While `loop` waits for work it prints `No work ready, retrying in Ns (attempt X of N)` to stderr between attempts, and a give-up line once the attempts are exhausted.

A controller failure — API error, malformed work item state, ambiguous identity — is a hard stop. Report it exactly; never retry around it or fall back to a guess.

## Step 2: Carry out `# Due Next`

`# Due Next` says what to do; do not keep your own table of what each stage or action means.

- **Autonomous `action`** (a `pdlc-*` skill name or `pdlc-post-ci`): fill [`references/handling-agent.prompt.md`](references/handling-agent.prompt.md) with `work_item_number` and the `# Due Next` section verbatim, spawn exactly one lightweight handling agent in the background, and wait for its output. The handling agent carries out that section's instruction — invoking the skill it names with the work item number, or running the `pdlc` command it names — the same way the `pdlc` skill's Continue mode acts on `# Due Next`. Then continue to Step 3.
- **`human-input`, `human-approval`, `human-decision`, or `blocked`**: **Stop**. Relay `current_status` and the `# Due Next` section to the driver as the action they must take; do not act on it yourself.
- **`none`**: **Stop**. Report the notice, and the `attempts` count when present; the script should be re-invoked later.

Never reconstruct context from the title or re-derive the stage yourself; the invoked skill resolves the record with `pdlc inspect` itself. A handling agent whose `# Due Next` tells it to stop and ask the user reports that back as a stop, never as a clean pass.

Never mutate work item state to claim work — the controller reads state, it doesn't lock it. Two agents possibly running is a coordination problem to raise, not fix with a state field.

## Step 3: Poll again, or stop

A pass that dispatched cleanly is not the end of the run: **return to Step 1 and poll again**. The controller decides what is next each time — never queue up several actions from one poll, and never predict the next action from the one that just finished. A record is only ever advanced by re-reading its state.

Stop, and stop the whole run, on the first of:

- Any human action from Step 2 — `human-input`, `human-approval`, `human-decision` — or `blocked` or `none`.
- Any controller error, malformed state, or ambiguous identity.
- Any specialist that fails, reports a blocker, returns an unexpected state, or leaves work it could not finish. Never move past it and pick up something else.
- **No forward progress**: a pass that returns the same `action` for the same record as the pass before it, with `current_status` unchanged. Repeating it will not help — report both passes and stop.
- The driver asked for a single pass.

Track the passes as you go and report them in order at the end: for each, the record acted on, the action dispatched, what the specialist returned, and the resulting `Status`/`Gate State`. Then name the stop condition that ended the run and what the driver has to do next. A run that stopped on a failure says so plainly — do not summarise it as a completed queue.

## Backoff

Only `none` retries, with exponential backoff: `min(initial × 2^(attempt-1), maximum)`. Errors and malformed state raise straight away. Each wait and the final give-up print to stderr so the caller sees why the loop returned.

Defaults: five attempts, 60s initial delay, 15-minute cap. Override with the `[workflow]` keys `max_attempts`, `initial_delay_seconds`, `max_delay_seconds` in `.pdlc/config.toml`. `[workflow] no_sleep = true` skips the waits (tests).

---

## Boundaries

- Do not author, plan, implement, test, verify, or review anything yourself — every action belongs to the skill or command `# Due Next` names.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`. The loop never approves, skips, or completes.
- Do not dispatch a non-autonomous action, and never treat a completed record as eligible.
- Do not continue past a stop condition, and do not keep polling a record that is not progressing.
- Do not invent work the controller did not return.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim a specialist's result, or a state transition, that did not actually happen.

## Checklist

- [ ] Asked the controller rather than deciding the next action yourself
- [ ] `action` was a `pdlc-*` skill name or `pdlc-post-ci` before dispatching; otherwise stopped
- [ ] Spawned one background handling agent from `references/handling-agent.prompt.md` with the returned `# Due Next` section verbatim, waited for its output, and let it carry out that instruction
- [ ] Stopped on `human-input`, `human-approval`, `human-decision`, `blocked`, `none`, or any controller error, relaying `# Due Next` as the driver's action
- [ ] Re-polled the controller after every clean pass rather than chaining a predicted next action
- [ ] Stopped on the first stop condition, including a pass that made no forward progress
- [ ] Reported every pass in order, the stop condition, and what the driver must do next
