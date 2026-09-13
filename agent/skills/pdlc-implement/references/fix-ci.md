# Fix red CI at Implementation

Follow this when `### Open Changes` lists a CI failure, or a Verification bounce for a red check. Every delivery task is already closed, so this path replaces Scope through Land: each fix lands on its closed task's own branch, and the stage publishes again. One run fixes every red check.

## Read the failure

```bash
pdlc inspect changes WORK_ITEM
```

A CI failure names the red pull requests and their rollup state, such as `#149 (FAILURE)`, not the checks. For each red PR, list its failing checks and read their logs on the code host; on GitHub, `gh pr checks PR` names them and `gh run view RUN_ID --log-failed` prints the failure. Map each red PR to its task with `pdlc inspect test WORK_ITEM`, which lists every closed task with its linked PRs.

A stacked PR's CI runs over every commit below it, so one cause turns its own PR and every PR above it red. Group the red checks by cause, and give each cause to the lowest task whose PR shows it.

This step is complete when every red check has a cause, a log excerpt, and an owning task.

## Classify each cause

- **Code**: the owning task's change breaks a build, test, lint, or type check. Fix it in the next step.
- **Flake**: it fails with no code cause, such as a runner outage, a timeout, a cancellation, or a test that passes on rerun. Rerun the failed jobs (`gh run rerun RUN_ID --failed`). Green needs no commit; red again on the same error is a code cause.
- **Upstream**: it fails on the base branch too, or the fix would change approved intent. Report the check, its log excerpt, and the reason to the driver, name `pdlc post invalidate` against the owning stage for an intent change, and stop.

This step is complete when every cause is labelled code, flake, or upstream.

## Fix each code cause, lowest task first

1. **Branch.** With the tree clean, as in Implement, run `gh stack checkout <branch>` for the owning task's branch.
2. **Dispatch** the task's `## Agent` implementer, from `pdlc inspect task DELIVERY_TASK`, with [`task-implementation-prompt.md`](task-implementation-prompt.md). The Gate evidence is the check name, its log excerpt, and the command that reproduces it. The fix is one new commit on top.
3. **Validate** with that reproduction command plus Implement's validation, and confirm the check passes locally.
4. **Review** the fix commit at task depth, as in Review.
5. **Re-land** the task without `--close`; it stays closed:

   ```bash
   pdlc post implement-task DELIVERY_TASK /tmp/pdlc-task-summary.md
   ```

   Write the summary as the task's whole implementation, the original plus this fix, starting from the current `## Implementation` in `pdlc inspect task DELIVERY_TASK`: re-landing replaces that comment and the PR description. The command resubmits the stack, so every branch above picks up the fix before you check out the next one.

This step is complete when every code cause has a reviewed fix commit on its owning branch, and each owning task's re-land JSON shows its `taskPr`.

## Publish

Watch every PR that was red to a result (`gh pr checks PR --watch`). Publish only when all of them are green; a red check is another pass through this file, and a third red on the same cause goes to the driver.

Run Publish with evidence naming each red check, its cause, and its fix commit or green rerun. This path is complete when the JSON shows `gateState: Review Required`; the stage review and CI run again from there.
