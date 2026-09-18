# Task implementation summary outline

`pdlc-implement` Land writes one summary of what was done per task and posts it
with `pdlc post implement-task`. It is a comment on the delivery task — the task
body and its `## Technical Plan` are never touched. The same text also becomes
the task PR's description, and the task's own title becomes the PR title, so
write the summary to read on the pull request too.

Write it so a reviewer who has not read the task or its `## Technical Plan` can
follow it. Use this structure exactly:

```md
Task: TASK-NNN. Base: pdlc/<slug>/task-<prev> (or trunk if first in the stack).

<What & why — the problem this task solves and the change, in 2-3 short
sentences.>

<Scope — what this task does and does not cover, including anything deferred to a
later task. 3-4 sentences.>

### Approach

<Key implementation decisions, tradeoffs, and any rejected alternative and why.
Skip mechanical detail the diff already shows. One line if there was nothing to
weigh.>

### Testing

<What was run and the result — static checks, tests, build, runtime. Call out
failed or decision-relevant checks explicitly; "full suite green" is enough for
routine passes.>

### Evidence

- Commit <sha> on the task PR for TASK-NNN.
- <anything worked around or left open, or omit this bullet if none>
```

Keep each section plain and tight. Keep every heading even when a section is one
line; do not pad it.

A re-land replaces the comment and the PR description outright, so the summary
is the task's whole implementation, starting from its current `## Implementation`
in `pdlc inspect task`, not just the fix. Add one Evidence bullet per thread,
check, or finding the fix addressed, naming it; on the top task, name the
request a cross-cutting fix came from, so reviewers see why code outside the
task is there.
