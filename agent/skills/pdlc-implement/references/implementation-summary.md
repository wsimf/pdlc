# Task implementation summary outline

`pdlc-implement` Step 5 writes one summary of what was done per task and posts it
with `pdlc post implement-task`. It is a comment on the delivery task — the task
body and its `## Technical Plan` are never touched.

Keep it to a few plain lines. Include only:

- **Shipped** — what the task now does, in one sentence.
- **Evidence** — commit and shared PR.
- **Validation** — only failed or decision-relevant checks; omit routine green checks.
- **Exception** — anything deferred, worked around, or left open (omit if none).

```md
Shipped: RouteProfileStore now persists geometry through RouteFileService.
Evidence: commit abc1234 on PR #148.
Exception: migration path for pre-existing profiles deferred to TASK-006.
```
