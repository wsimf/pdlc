---
name: pdlc-loop
description: "Poll the PDLC queue for the next autonomous work item, dispatch the specialist skill the controller names, and stop as soon as a human is required. Use when asked to run the PDLC queue, pick up the next item, or continue autonomous PDLC work."
argument-hint: "Optional work item number to prioritise"
disable-model-invocation: true
---

# Run the PDLC queue

This skill decides nothing about the work itself. It asks the controller what is next, hands the returned instruction to the specialist skill named in it, and stops the moment a human is required. Routing lives in the controller; the work lives in the specialists.

Read `references/loop-contract.md` for the retry contract, and `../pdlc/references/parity-contract.md` before dispatching.

## Required input

None. With no argument the controller scans the whole queue. An work item number prioritises that one record — pass it through verbatim, never infer one from the branch, recent files, or open PRs.

---

## Step 1: Ask the controller what is next

```bash
pdlc next loop
pdlc next loop WORK_ITEM   # one record
```

Returns a Markdown document: YAML front matter — `id`, `work_item_number`, `title`, `current_status`, `next_status`, `action` — then a one-line instruction. `action` is a `pdlc-*` skill name, or `human-approval` / `blocked` / `none`. An exhausted no-work scan carries `action: none` with an `attempts` count instead.

The scan skips anything not autonomous (`Product` never surfaces — that needs the driver), and auto-advances past any `Skipped States` stage before deciding.

While `loop` waits for work it prints `No work ready, retrying in Ns (attempt X of N)` to stderr between attempts, and a give-up line once the attempts are exhausted.

A controller failure — API error, malformed work item state, ambiguous identity — is a hard stop. Report it exactly; never retry around it or fall back to a guess.

## Step 2: Act on `action`

| `action` | What to do |
|---|---|
| a `pdlc-*` skill name | Invoke that skill for `work_item_number`. Continue to Step 3. |
| `pdlc-post-ci` | An `Implementation / CI Pending` record whose checks have settled. Run `pdlc post ci <work_item_number>` — it sets `Approval Required` (green) or `Changes Required` (red, with a `PDLC-IMPLEMENTATION` note). Report the outcome, then Step 3. Do not invoke a skill for this action. |
| `human-approval` | Record is at `Approval Required`. **Stop**, tell the driver which record and stage (`current_status`) awaits them. |
| `human-decision` | Record is at `Decision Required` — a reviewer or the Verification audit raised a blocking finding only the driver can resolve. **Stop**, point the driver at the `PDLC-DECISION` comment; they resolve it via the `pdlc` skill's decision-resolver workflow. No reconciliation is attempted. |
| `blocked` | Work item state, work type, or pipeline is malformed, unsupported, or unavailable. **Stop**, report `current_status` and the controller's reason exactly. |
| `none` | Nothing actionable; scan exhausted. **Stop**, report the `attempts` count and that the script should be re-invoked later. |

Invoke the named skill with just `work_item_number` — it resolves the record with `pdlc inspect` itself, and reads `pdlc inspect timeline <work-item>` when it needs the evidence trail (reviewer findings, recorded approvals). Never reconstruct context from the title or re-derive the stage yourself. `pdlc post ci` is the exception: it is not a skill — run the command named in the row and report its JSON.

A `CI Pending` record whose checks are still running comes back as `none` (reason names the record) so the loop backs off and re-polls, exactly as for an empty queue — you never dispatch anything for it until `pdlc next` returns `pdlc-post-ci`.

Never mutate work item state to claim work — the controller reads state, it doesn't lock it. Two agents possibly running is a coordination problem to raise, not fix with a state field.

## Step 3: Report the pass and stop

Report the record acted on, the action dispatched, what the specialist returned, and the resulting `Status`/`Gate State`.

One instruction per invocation — don't chain into a second poll yourself; the driver decides whether the queue keeps running. Stop immediately on any specialist failure, blocker, or unexpected state rather than moving on and leaving it behind.

## Backoff

Only `none` retries, with exponential backoff: `min(initial × 2^(attempt-1), maximum)`. Errors and malformed state raise straight away. Each wait and the final give-up print to stderr so the caller sees why the loop returned.

Defaults: five attempts, 60s initial delay, 15-minute cap. Override with `PDLC_MAX_ATTEMPTS`, `PDLC_INITIAL_DELAY_SECONDS`, `PDLC_MAX_DELAY_SECONDS`. `PDLC_NO_SLEEP` skips the waits (tests).

---

## Boundaries

- Do not author, plan, implement, test, verify, or review anything yourself — every action belongs to the skill the controller named.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`. The loop never approves, skips, or completes.
- Do not dispatch a non-autonomous action, and never treat a completed record as eligible.
- Do not invent work the controller did not return.
- Preserve unrelated staged, unstaged, and untracked local work.
- Do not claim a specialist's result, or a state transition, that did not actually happen.

## Checklist

- [ ] Asked the controller rather than deciding the next action yourself
- [ ] `action` was a `pdlc-*` skill name (or `pdlc-post-ci`) before dispatching; otherwise stopped
- [ ] Invoked the named skill with the work item number and let it inspect the record itself, or ran `pdlc post ci` for a `pdlc-post-ci` action
- [ ] Stopped on `human-approval`, `human-decision`, `blocked`, `none`, or any controller error
- [ ] Ran exactly one instruction and reported the record's resulting state
