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

## Fixing a finding

Fix the cause, not the symptom. A symptom fix leaves the real defect in place
and makes the next one harder to find.

- Reproduce the failure before you change anything, so you can tell a fix from
  a coincidence.
- Ask why the failure happens until the answer is a line of code, not a
  condition you can guard against.
- A guard that only silences the symptom is not a fix: a nil check that stops a
  crash, a retry around a call that should not fail, a catch that swallows the
  error, a default that hides a missing value.
- If a fix needs a paragraph of comment to justify it, the code is wrong. Fix
  the code (not the comment).
- Fix the pattern, not the instance: search the files this fix owns for the
  same shape and fix every one you find there. Report the ones outside those
  files rather than widening the change.
- When a failure follows a restart, a rerun, or a fresh checkout, suspect stale
  state before code — caches, lock files, serialised state, generated output.
- When you are stuck, instrument. Add logging, read the actual error, print the
  real value. Do not guess at the cause.

**Two failed fixes at the same gate stop the loop.** When a second fix fails the
same check, the premise both fixes shared is the suspect, not the fixes. Do not
write a third. Write that premise down in one sentence, and report it with what
each attempt changed and how each failed. That is a decision for a human, not a
retry.

## Shape of the change

Make the smallest change that satisfies the task, and leave the code you touch
simpler than you found it. Removals stay inside the files this task owns —
anything wider is a line in your report, not a change.

- Subtract before you add. Dead code, a stub, a redundant validator, or a
  decision duplicated across the files you are touching goes first; build on
  the smaller base.
- Fewer lines beat elegant boilerplate. A wrapper, layer, or abstraction with
  one caller is not worth its indirection.
- Do not repeat a decision in several places. Put it behind one source of truth
  and pass the result.
- Do not thread a new signal through types, schemas, or pipelines when a direct
  path exists. Where the plan asks for the threading, follow the plan and say
  in your report where the direct path would have done.
- When this task replaces an internal API, migrate its callers and delete the
  old one here. A compatibility shim kept only because internal callers still
  exist is dual-path complexity, not a migration.
- If answering a question about this code takes tracing through more than about
  three files, the shape is wrong.

Types and boundaries:

- Make illegal states unrepresentable. Model variants as a sum type rather than
  a bag of optional fields whose contradictory combinations still compile. If
  you could write a comment explaining which combinations are valid, the type
  is too loose.
- Give distinct meanings distinct types. Two parameters that share a primitive
  type and mean different things should not be interchangeable.
- Parse external data at the boundary — CLI arguments, config, network
  payloads, stored rows — into the typed model, then trust the types inside. A
  nil check deep in a call chain the boundary already covered is noise.
- Do not lie to the compiler. A cast, force-unwrap, or assertion that bypasses
  a fact you cannot prove is a runtime failure in waiting: prove it, model it
  away, or report that you could not.
- Match on a variant exhaustively, so a variant added later fails the build
  instead of falling through silently.

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
