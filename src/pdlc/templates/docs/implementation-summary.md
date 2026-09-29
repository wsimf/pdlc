# Implementation summary

Write this as the description of the delivery task's pull request for a reviewer who has not read the task or its `## Technical Plan`. The same text becomes the task's `## Implementation` comment; the task body and plan stay untouched. Describe the whole PR as it stands now, not just the latest commit or review fix.

```md
### What

- <The result a user or caller can observe, and the scope of this task's PR. Link the task for detail, but make this section understandable on its own.>

### Why

- <The problem or goal this change addresses, including the relevant product or engineering context.>

### How

- <The approach and significant design decisions a reviewer should understand. Explain choices the diff alone cannot make clear; do not inventory files or commits.>

### Testing

- <The checks actually run, their results, any manual verification, and relevant gaps or risks. Do not claim a check that was not run.>

### Anything else <!-- optional -->

- <Review focus, tradeoffs, accepted findings, limitations, or follow-up work that matters to this PR.>

---
Stacked on #NNN; this task's work starts at <sha>.
```

Use concise prose or bullets, whichever makes the PR easiest to review. `### What`, `### Why`, `### How`, and `### Testing` are required and must have real content. Omit an optional heading entirely when it adds nothing; never leave a placeholder. Include a task link when available, but do not make the reviewer follow it to understand the change. Keep routine details brief and give failures, skipped checks, workarounds, and meaningful risks enough detail to assess. Omit the stack footer for the first task, whose base is trunk.

On a re-land, read the existing PR description and the current task implementation, then revise this whole description against the code now on the branch and the latest agent and test reports. Preserve still-true context and any useful human edits; update sections affected by review feedback, invalidation, or changed verification. Do not copy a configured PR-only attachment line into this summary; the CLI adds that line to the PR body. The PR body must describe the complete current change, never only the latest adjustment or a chronological fix log.
