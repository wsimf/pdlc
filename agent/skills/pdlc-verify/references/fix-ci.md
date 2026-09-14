# Route red CI at Verification

Follow this when `pdlc inspect changes WORK_ITEM` lists a CI failure: a clean verification landed `CI Pending`, and the stack's checks came back red. Verification is source-read-only, so every red check with a code cause is a **Fix** finding, bounced to its owning stage.

## Read the failure

A CI failure names the red pull requests and their rollup state, such as `#149 (FAILURE)`, not the checks. For each red PR, list its failing checks and read their logs on the code host; on GitHub, `gh pr checks PR` names them and `gh run view RUN_ID --log-failed` prints the failure. `pdlc inspect test WORK_ITEM` maps each PR to its task.

A stacked PR's CI runs over every commit below it, so one cause turns its own PR and every PR above it red. Group the red checks by cause, and trace each to the commit that introduced it.

This step is complete when every red check has a cause, a log excerpt, and the commit behind it.

## Classify each cause

- **Production**: production code breaks a build, test, lint, or type check. It bounces to `Implementation`.
- **Coverage**: an acceptance test, its fixture, or its harness is wrong. It bounces to `Testing`.
- **Flake**: it fails with no code cause, such as a runner outage, a timeout, a cancellation, or a test that passes on rerun. Rerun the failed jobs (`gh run rerun RUN_ID --failed`) and watch them to a result (`gh pr checks PR --watch`). Green needs no bounce; red again on the same error is a production or coverage cause.
- **Upstream**: it fails on the base branch too. Report the check, its log excerpt, and the base-branch run to the driver, and stop.

This step is complete when every cause is labelled production, coverage, flake, or upstream, and an upstream cause has stopped the run.

## Post

Any production or coverage cause is a bounce. Write a short report fragment with one line per cause, naming its PR, check, owning task, and log excerpt, and say the audit sections did not re-run. Post it through the skill's Post step with `--recommendation "Changes Required"` and `--bounce STAGE`, naming the earliest stage that must rework: `Implementation` whenever any cause is production, otherwise `Testing`. This path is complete when the JSON shows the bounced stage in `bouncedTo`.

When every cause went green on rerun, re-post the latest clean run's report fragment unchanged through the skill's Post step with `--recommendation "Approval Required"`. Its `Verified @` commits still hold, since no source changed. This path is complete when the JSON's `gateState` is `Approval Required`, or `CI Pending` while the checks rerun.
