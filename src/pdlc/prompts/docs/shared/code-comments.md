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
