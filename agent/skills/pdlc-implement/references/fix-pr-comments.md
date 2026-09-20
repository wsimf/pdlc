# Fix PR comments policy

`pdlc prompt task-implementer WORK_ITEM --file` builds the brief whenever the unit's `#### Unresolved threads` lists review threads, filling in the pull request, the task, its `## Technical Plan`, and the driver's `#### Decisions` from the record. This file covers what the skill decides once that agent returns.

The agent knows nothing about the PDLC pipeline: it sees one pull request, its open threads, and the working tree. Tell it nothing about stages, gates, or the parent work item. It commits but never pushes — the branch, the re-land, and the stage evidence stay with the skill.

A comment the agent judges invalid, or one that diverges from the agreed Technical Plan or acceptance criteria or turns on a product, architecture, UX, safety, or scope call, is not this skill's to settle. The agent skips it, leaves the thread untouched, and reports it back with its reasoning; the skill lands the other fixes, then escalates every skipped thread as a decision (see `SKILL.md` Escalate). The driver closes a thread that does not apply, or leaves it open to have it applied on the next pass.

A thread the driver answers comes back under the unit's `#### Decisions` on a later pass, and the brief carries that answer forward; a thread named there that is still open has been approved for implementation whatever the agent judged earlier.
