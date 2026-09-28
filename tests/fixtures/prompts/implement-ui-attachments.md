You are implementing one delivery task's production code. Commit your work on
the current branch before you report back, leaving nothing uncommitted; do not
push, branch, or open a pull request.

## Execution boundary

You are being invoked as a leaf worker for this one task.

Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Implement the task below directly and return one report.

## Task

`WORK-60-TASK-001` (tag included) — `[UI] Screen`

## Scope
Build the screen.

Covers FR-1.

## Acceptance criteria
- it works

## Technical Plan

Touch one module.

## Context

- Parent work item: `60`.
- Requirements and constraints this task covers: - FR-1: The record lands.
- Upstream tasks it depends on, and what each shipped: none
- For a UI task: the approved `UJ-*` journey text it covers: none
  Project design-system and platform constraints are already covered by
  `AGENTS.md` / `CLAUDE.md`.

## Attachments

Files attached to the work item, such as mockups or screenshots. Read the ones that inform your task. Where a Figma or other mockup covers a UI journey, follow that design as closely as possible.

1. Primary navigation mockup
  - Path: $PDLC_HOME/60/attachments/att_4597f8b310a1c49556df76c44c94a7b40c1e04d4b7b015c54519b4b30457bffa.png
2. att_8902eec15e01d879d27e127f86f0ea271626438e4f0552b69d6200254371fb0f.png
  - Path: $PDLC_HOME/60/attachments/att_8902eec15e01d879d27e127f86f0ea271626438e4f0552b69d6200254371fb0f.png

## Ownership and rules

- Leave unrelated code, staged work, and untracked files alone.
- The current branch is already correct — do not create, switch, or rename a
  branch.
- Commit on top of what is already on the branch — never amend, rebase, or squash existing commits, including your own from an earlier dispatch. Do not push; do not open or touch a pull request.
- Implement production code only. Do not create, edit, or delegate tests — coverage is owned separately.
- Stay inside the approved contract. If the plan is insufficient or wrong, stop and report rather than expanding scope.

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

The commits you made, the files changed, the validation actually run, the acceptance criteria
verified against the running app and their outcome, and any point where the
plan did not fit the code.
