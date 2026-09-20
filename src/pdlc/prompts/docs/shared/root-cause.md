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
