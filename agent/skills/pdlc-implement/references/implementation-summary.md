# Task implementation summary outline

`pdlc-implement` Land writes one summary of what was done per task and posts it
with `pdlc post implement-task`. It is a comment on the delivery task — the task
body and its `## Technical Plan` are never touched. The same text also becomes
the task PR's description, and the task's own title becomes the PR title, so
write the summary to read on the pull request too.

The skill fills this outline itself, from the agents' reports and the validation
it saw, and hands the resulting file to `pdlc post implement-task`.

Write what the diff cannot tell a reviewer who has not read the task or its
`## Technical Plan`: why the change exists, and anything about it they would
otherwise stop and question.

```md
### Why

- <the problem this task solves>

### What changed

- <behaviour a reviewer can observe, not the files that moved>

### Decisions

- <a call a reviewer would question, with the alternative rejected and why>
- <a constraint or workaround that explains a shape that looks wrong>
- <anything deliberately left undone, and what it waits on>

### Verified

- <what was run and its result>

---
Stacked on #NNN; this task's work starts at <sha>.
```

One sentence per bullet, two where a decision needs its alternative named. A
bullet that runs to a paragraph belongs in the task's `## Technical Plan` or in a
comment next to the code, not here. Most headings carry one or two bullets.

`### Why`, `### What changed`, and `### Verified` are always present. Drop
`### Decisions`, heading included, when the task had no call to explain; never
leave a heading standing over a placeholder. Never write a bullet that restates
the diff, names files, or lists commits — the pull request already shows those.
Under `### Verified`, one line covers a routine green run, while a failure, a
skipped check, or a workaround gets the detail a reviewer needs to judge it. Omit
the footer for the first task in a stack, whose base is trunk.

A re-land replaces the comment and the PR description outright, so the summary
is the task's whole implementation, starting from its current `## Implementation`
in `pdlc inspect task`, not just the fix. What the fix answered — a review
thread, a failing check — stays in the pull request's own history; repeat it
here only where it changed the implementation in a way the bullets above need to
explain.
