# Stage-reviewer dispatch prompt

`pdlc-review` Step 3 fills the placeholders below and spawns the agent named in
`pdlc inspect review`'s `## Reviewer Target` once with the result. The
reviewer cannot see the driver's conversation, so everything it needs is stated
here. Read-only: it returns findings and a verdict, and changes nothing.

---

```md
Independently review the artifact below for the named PDLC stage.

## Record

- Parent work item: `<number>` — work item ID: `<id>`.
- Complete parent work item body:

<full body>

- Active `Status` / `Gate State`, as read: `<...>`.

## Artifact under review

From `## Reviewer Target`: `<the exact artifact>`.

For an **Implementation** review only — depth: `<pass | task | full>`. Name the
task or journey when depth is `task`. Send no depth to any other reviewer.

## Scope evidence

<hand over exactly what this stage's reviewer needs, so it never guesses scope:>

- **UI / Tasks** — the task tree; no source diff.
- **Technical Plan** — the task bodies with their `## Technical Plan` comments,
  plus the source files those plans claim to own.
- **Implementation** — the linked PR numbers, their diffs, their check state, and
  each task's `## Implementation` comment.
- **Testing** — the PR carrying the test commits, the coverage map, CI results,
  and the requirements they claim to trace.

## Prior findings (re-review only)

`<the previous review's findings, so each can be confirmed addressed — or "none,
first review">`

## Driver follow-up

`<verbatim, or "none">`

## Report back

Actionable findings with evidence, changed prior-finding status, and exactly
one of `Approval Required`, `Changes Required`, or `Decision Required`. On a
re-review, omit unchanged findings, scope, coverage boundaries, and validation
history. A clean review is one line naming the artifact and PR/commit.

Use `Decision Required` when at least one finding cannot be reconciled
mechanically from source and spec — it needs a product, architecture, UX, or
scope call from the driver. With that verdict, include a `## Decision Required`
section: the question, the options and their trade-offs, your recommendation,
what it blocks, and why it is not a mechanical fix. This halts the autonomous
loop; do not reach for it for anything the owning skill could just fix.
```
