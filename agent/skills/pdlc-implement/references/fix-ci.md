# Classify a red check

Follow this from `pdlc-implement` Implement when the unit's `#### Failing checks` lists a red pull request. It turns each red check into a finding for the task prompt, a rerun, or a driver report; the skill dispatches, reviews, and re-lands the fix.

## Read the failure

The unit names the red pull request and its rollup state, such as `PR #149: FAILURE`, not the checks. List its failing checks and read their logs on the code host; on GitHub, `gh pr checks PR` names them and `gh run view RUN_ID --log-failed` prints the failure.

A stacked PR's CI runs over every commit below it, so a cause in a lower task turns this PR red too. A check that fails on this task's own change is this unit's; one whose log points at a lower task's code is that task's, and `pdlc inspect implement` offers the lower task first, so report it and take the next pass instead of fixing it here.

This step is complete when every red check has a cause and a log excerpt.

## Classify each cause

- **Code**: this task's change breaks a build, test, lint, or type check. It is a finding for the task prompt: the check name, its log excerpt, and the command that reproduces it. Validation for the fix includes that command passing locally.
- **Flake**: it fails with no code cause, such as a runner outage, a timeout, a cancellation, or a test that passes on rerun. Rerun the failed jobs (`gh run rerun RUN_ID --failed`). Green needs no commit; red again on the same error is a code cause.
- **Upstream**: it fails on the base branch too, or the fix would change approved intent. Report the check, its log excerpt, and the reason to the driver. For an intent change, execute `pdlc post invalidate` against the owning stage when authorized; otherwise request that authorization. Stop this fix path.

This step is complete when every cause is a finding in the brief, green on rerun, or reported to the driver.
