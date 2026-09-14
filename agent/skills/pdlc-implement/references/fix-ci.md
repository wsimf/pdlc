# Diagnose red CI at Implementation

Follow this from [`rework.md`](rework.md) for each CI failure it lists, or a Verification bounce for a red check. It turns red checks into findings with owning tasks; `rework.md` fixes, re-lands, and publishes them.

## Read the failure

A CI failure names the red pull requests and their rollup state, such as `#149 (FAILURE)`, not the checks. For each red PR, list its failing checks and read their logs on the code host; on GitHub, `gh pr checks PR` names them and `gh run view RUN_ID --log-failed` prints the failure. Map each red PR to its task with `pdlc inspect test WORK_ITEM`, which lists every closed task with its linked PRs.

A stacked PR's CI runs over every commit below it, so one cause turns its own PR and every PR above it red. Group the red checks by cause, and give each cause to the lowest task whose PR shows it.

This step is complete when every red check has a cause, a log excerpt, and an owning task.

## Classify each cause

- **Code**: the owning task's change breaks a build, test, lint, or type check. Hand it to `rework.md` as a finding: the check name, its log excerpt, the command that reproduces it, and the owning task. Validation for its fix includes that command passing locally.
- **Flake**: it fails with no code cause, such as a runner outage, a timeout, a cancellation, or a test that passes on rerun. Rerun the failed jobs (`gh run rerun RUN_ID --failed`). Green needs no commit; red again on the same error is a code cause.
- **Upstream**: it fails on the base branch too, or the fix would change approved intent. Report the check, its log excerpt, and the reason to the driver, name `pdlc post invalidate` against the owning stage for an intent change, and stop.

This step is complete when every cause is a finding handed to `rework.md`, green on rerun, or reported to the driver.
