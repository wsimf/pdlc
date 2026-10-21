# Route red CI at Verification

Follow this when `pdlc inspect changes WORK_ITEM` lists a CI failure: a clean verification landed `CI Pending`, and the stack's checks came back red. Verification is source-read-only, so every red check with a code cause is a **Fix** finding, bounced to its owning stage.

## Read the failure

A CI failure names the red pull requests and their rollup state, such as `#149 (FAILURE)`, not the checks. Run `pdlc inspect checks WORK_ITEM` to list each red PR's checks. Prefer it over `gh pr checks` or other direct `gh` calls: PDLC may be filtering out checks the user intentionally marked as ignored, and any failure on those is discarded, never investigated, rerun, or fixed; `pdlc config ignored_checks` lists them. Read each failing check's log on the code host; on GitHub, `gh run view --job JOB_ID --log-failed` prints it, where the check's link ends in `runs/RUN_ID/job/JOB_ID`. `pdlc inspect test WORK_ITEM` maps each PR to its task.

A stacked PR's CI runs over every commit below it, so one cause turns its own PR and every PR above it red. Group the red checks by cause, and trace each to the commit that introduced it.

This step is complete when every red check has a cause, a log excerpt, and the commit behind it.

## Classify each cause

- **Production**: production code breaks a build, test, lint, or type check. It bounces to `Implementation`.
- **Coverage**: an acceptance test, its fixture, or its harness is wrong. It bounces to `Testing`.
- **Flake**: it fails with no code cause, such as a runner outage, a timeout, a cancellation, or a test that passes on rerun. Rerun the failed jobs (`gh run rerun RUN_ID --failed`), watch them to a result (`gh run watch RUN_ID`), and confirm it in `pdlc inspect checks WORK_ITEM`. Green needs no bounce; red again on the same error is a production or coverage cause.
- **Upstream**: it fails on the base branch too. Report the check, its log excerpt, and the base-branch run to the driver, and stop.

This step is complete when every cause is labelled production, coverage, flake, or upstream, and an upstream cause has stopped the run.

## Post

Any production or coverage cause is a bounce. Raise one open finding per cause, naming its PR, check, owning task, and log excerpt, and leave every row the report does not carry forward `not_run`. Set `bounce` to the earliest stage that must rework: `Implementation` whenever any cause is production, otherwise `Testing`. Post it through the skill's Post step. This path is complete when the JSON shows the bounced stage in `bouncedTo`.

When every cause went green on rerun, no source changed, so the report `pdlc inspect verify` wrote carries every row forward; post it unchanged through the skill's Post step. This path is complete when the JSON's `gateState` is `Approval Required`, or `CI Pending` while the checks rerun.
