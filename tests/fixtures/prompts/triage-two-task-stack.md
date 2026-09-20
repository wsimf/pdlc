## Objective

The branches below are a stack of pull requests that together implement one
feature, lowest first; each higher branch builds on the one beneath it. A
reviewer has asked for changes to that implemented work. Investigate the
current implementation thoroughly before changing anything: read the code each
request names, its callers, and its tests, on the branch that owns it. Then
place each finding on the branch of the task it belongs to and fix it there.

## Requests

### Change request — 2026-04-01 00:00 UTC

## Findings

- detail

## Stack

### pdlc/record-60/task-001 — `WORK-60-TASK-001` `[CORE] First`

Touch one module.

### pdlc/record-60/task-002 — `WORK-60-TASK-002` `[UI] Second`

Touch one module.

The last entry above is the top branch, and it is the one currently checked out.

## Execution boundary

You are being invoked as a leaf worker for this one set of requests.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Switch only between the branches listed under `## Stack`, with `git checkout`;
do not create, rename, rebase, or merge a branch, and do not push.

## Workflow

1. **Split** each request into findings: one concrete change each.
2. **Place** each finding on the branch of the task whose plan owns the code it
   changes. When no task clearly owns it, when it spans tasks, when it only
   adds new files, or when its fix needs a fix you are making on a lower
   branch, place it on the top branch instead. A higher branch does not
   contain what you commit on a lower one until the stack is later rebased.
3. **Fix** lowest branch first: check out the branch, implement the finding,
   verify with the relevant project command, and commit there with a message
   naming the request it answers. Never amend, rebase, or squash existing
   commits. Then move up.
4. A finding the current code already meets needs no change; note it with the
   evidence.
5. Stop and report, without committing anything for it, when a finding
   requires a product, architecture, UX, safety, or scope decision, or when
   fixing it would change what a task was specified to do. Name the request it
   came from and its link, so the call can be put to a human as it stands.
6. Finish on the top branch, with a clean tree on every branch you touched.

## Code comments

Write a comment only where the code cannot say it itself. Clear code needs no
comment, and a rename or a smaller function beats a line of English explaining
a confusing one.

A comment never carries the work. It names no work item, delivery task,
requirement, journey, pull request, or branch, and it repeats no scope,
non-goal, or acceptance criterion from the task. A tag like
`WORK-12-TASK-003`, a reference to `FR-4`, or a line reading "added for the
auth task" sends the next reader to a record instead of the code, and goes
stale as soon as the code moves.

A comment describes the code as it stands today, never the change that
produced it. Drop "new", "now handles", "updated to", and "previously"; the
diff and the history own that story.

What earns a comment:

- A decision the code cannot show: why this approach rather than the obvious
  one, or what breaks if the order changes.
- A contract or ownership boundary: what a caller may assume, and what this
  code refuses to do.
- A constraint imposed from outside: a platform bug worked around, a call that
  must happen on a particular thread, a limit the API sets.

What does not:

- A restatement of the line below it.
- A name the code should carry instead. Rename the symbol.
- A TODO pointing at work nobody has agreed to. Report it instead.

Keep every comment you touch true. A comment that no longer matches the code
costs the reader more than no comment at all.

## Report back

One entry per finding: the request it came from, the disposition (fixed,
already met, or needs a decision), the branch and commit for a fix or the
evidence for an already-met one, and one sentence on why it belongs on that
branch. Then the validation actually run, and any point where a plan did not
fit the code. Do not repeat the requests.
