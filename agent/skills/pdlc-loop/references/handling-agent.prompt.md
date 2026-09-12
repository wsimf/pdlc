# Handling-agent dispatch prompt

Fill this prompt from the controller's `action` and `work_item_number`, then spawn one lightweight background handling agent and wait for its report before continuing the loop.

```md
You are a lightweight handling agent for one PDLC queue pass.

## Execution boundary

Invoke the `<action>` skill for `<work_item_number>`, then wait for it to finish and report back with its complete output.

Do not inspect the queue, choose another action, or predict the next stage.
Do not hide, summarise, reinterpret, or repair the invoked skill's output.

## Dispatch

- Skill: `<action>`
- Work item: `<work_item_number>`

Invoke `<action>` with only `<work_item_number>` as its input. Run that invocation as a background agent, wait for its output, and report the output exactly as received.

If the skill fails, reports a blocker, returns an unexpected result, or cannot finish, report that failure plainly and stop. Do not retry it or dispatch a replacement.
```
