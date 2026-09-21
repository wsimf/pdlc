# Fix red CI at Testing

Follow this when `pdlc inspect changes WORK_ITEM` lists a CI failure, or a Verification bounce for a red check. The acceptance suite rides on the top task PR, and the whole stack's CI gates this stage, so a red check comes either from the coverage or from production code beneath it. This skill fixes only coverage.

## Read the failure

A CI failure names the red pull requests and their rollup state, such as `#149 (FAILURE)`, not the checks. For each red PR, list its failing checks and read their logs on the code host; on GitHub, `gh pr checks PR` names them and `gh run view RUN_ID --log-failed` prints the failure. `pdlc inspect test WORK_ITEM` maps each PR to its task.

A stacked PR's CI runs over every commit below it, so one cause turns its own PR and every PR above it red. Group the red checks by cause, and trace each to the commit that introduced it: an acceptance-coverage commit on the top task branch, or a task's production commit.

This step is complete when every red check has a cause, a log excerpt, and the commit behind it.

## Classify each cause

- **Coverage**: an acceptance test, its fixture, or its harness is wrong: it asserts behaviour the requirements never promised, or fails for a reason inside the test. Fix it in the next step.
- **Defect**: production code breaks an in-scope requirement, or a check fails on a lower task's PR. Production source belongs to Implementation. Report the check, its log excerpt, and the owning task to the driver, name `pdlc post invalidate WORK_ITEM Implementation --task TASK_NUMBER` as the route, and stop.
- **Flake**: it fails with no code cause, such as a runner outage, a timeout, a cancellation, or a test that passes on rerun. Rerun the failed jobs (`gh run rerun RUN_ID --failed`). Green needs no commit; red again on the same error is a coverage or defect cause.
- **Upstream**: it fails on the base branch too. Report the check, its log excerpt, and the base-branch run to the driver, and stop.

This step is complete when every cause is labelled coverage, defect, flake, or upstream, and a defect or upstream cause has stopped the run.

## Fix coverage

The current branch must be the top task branch the Testing PR tracks, since `pdlc post test` resolves the PR from it; on any other branch, report and stop.

Dispatch `pdlc-test-writer` once for every coverage cause, handing it the brief as the skill's Dispatch step does, built with `pdlc prompt acceptance-test-writer WORK_ITEM --traceability MAP_FILE --findings FINDINGS_FILE --file`: the map file holds the `## Traceability` map from the latest `PDLC-TESTING` evidence, and the findings file holds each coverage cause's check name and log excerpt. It commits on the current branch and never pushes; neither do you. Re-run `pdlc post test` to publish the fix commits to the stack along with the updated evidence.

This step is complete when its report is in, its fix commits are inspected, and `pdlc post test` has pushed them.

## Publish

Run the skill's Publish step with the same traceability map, updated only where coverage changed, and evidence naming each red check, its cause, and its fix commit or green rerun. `pdlc post test` pushes the fix commits as part of that publish, so the checks rerun only after it; then watch the red PRs to a result (`gh pr checks PR --watch`). Green ends this path. Red again is another pass through this file, and a third red on the same cause goes to the driver.

This path is complete when the stage lands at `Review Required` and the watched checks are green.
