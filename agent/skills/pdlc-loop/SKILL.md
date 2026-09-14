---
name: pdlc-loop
description: "Poll the PDLC queue, dispatch the specialist skill the controller names, and keep polling until a human is required. Use when asked to run the PDLC queue, pick up the next item, or continue autonomous PDLC work."
argument-hint: "Optional work item number to prioritise"
disable-model-invocation: true
---

# Run the PDLC queue

Run the queue until a human is required. `pdlc next loop` names what is next, one handling agent carries it out through the specialist skill or command it names, and you poll again. This skill decides nothing about the work itself.

Use [`references/handling-agent.prompt.md`](references/handling-agent.prompt.md) as the dispatch template.

## Resolve

No argument is required. With none, the controller scans the whole queue. A work item number prioritises that one record — pass it through verbatim, never infer one from the branch, recent files, or open PRs.

The run is autonomous by default: it keeps polling and dispatching until something needs a human. A driver who wants one action and a report says so ("just the next action", "one pass") — then Repeat stops after the first. This step is complete when the optional work item number and the single-pass request, if any, are known.

## Poll

```bash
pdlc next loop
pdlc next loop WORK_ITEM   # one record
```

The record's `# Due Next` section is the instruction for this pass. The front matter's `action` says whether you may carry it out: a `pdlc-*` skill name or `pdlc-post-ci` is autonomous; `human-input`, `human-approval`, `human-decision`, and `blocked` are stops; `none` means there is nothing to act on yet. See `pdlc next --help` for the full output.

A controller failure — API error, malformed work item state, ambiguous identity — is a hard stop. Report it exactly; never retry around it or fall back to a guess. This step is complete when the poll returned an `action` and its `# Due Next` section.

## Dispatch

`# Due Next` says what to do; do not keep your own table of what each stage or action means.

- **Autonomous `action`** (a `pdlc-*` skill name or `pdlc-post-ci`): fill [`references/handling-agent.prompt.md`](references/handling-agent.prompt.md) with `work_item_number` and the `# Due Next` section verbatim, spawn exactly one lightweight handling agent in the background, and wait for its output. Then continue to Repeat.
- **`human-input`, `human-approval`, `human-decision`, or `blocked`**: **Stop**. Relay `current_status` and the `# Due Next` section to the driver as the action they must take; do not act on it yourself.
- **`none`**: **Stop**. Report the notice, and the `attempts` count when present, and say the run should be re-invoked later.

Never reconstruct context from the title or re-derive the stage yourself. A handling agent whose `# Due Next` tells it to stop and ask the user reports that back as a stop, never as a clean pass.

Never mutate work item state to claim work. If two agents may be running on the same queue, raise it with the driver. This step is complete when the handling agent's output is in, or the run has stopped.

## Repeat

A pass that dispatched cleanly is not the end of the run: **return to Poll**. Never queue up several actions from one poll, and never predict the next action from the one that just finished.

Stop, and stop the whole run, on the first of:

- Any human action from Dispatch — `human-input`, `human-approval`, `human-decision` — or `blocked` or `none`.
- Any controller error, malformed state, or ambiguous identity.
- Any specialist that fails, reports a blocker, returns an unexpected state, or leaves work it could not finish. Never move past it and pick up something else.
- **No forward progress**: a pass that returns the same `action` for the same record as the pass before it, with `current_status` unchanged. Repeating it will not help — report both passes and stop.
- The driver asked for a single pass.

This step is complete when a stop condition has ended the run.

## Report

Report the passes in order: for each, the record acted on, the action dispatched, what the specialist returned, and the resulting `Status`/`Gate State`. Then name the stop condition that ended the run and what the driver has to do next.

A run that stopped on a failure says so plainly — do not summarise it as a completed queue. The report is complete when it lists every pass, the stop condition, and the requested human action.

## Boundaries

- Do not author, plan, implement, test, verify, or review anything yourself — every action belongs to the skill or command `# Due Next` names.
- Do not run `pdlc post approve`, `pdlc post skip`, `pdlc post invalidate`, or `pdlc post complete`; those are driver actions.
- Do not dispatch a non-autonomous action, and never treat a completed record as eligible.
- Do not continue past a stop condition, and do not keep polling a record that is not progressing.
- Do not invent work the controller did not return.
- Preserve unrelated staged, unstaged, and untracked work.
- Do not claim a specialist's result, or a state transition, that did not actually happen.
