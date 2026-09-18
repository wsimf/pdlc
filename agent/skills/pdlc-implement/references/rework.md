# Rework closed tasks

Follow this when `### Open Changes` lists change requests and `pdlc inspect implement` has no eligible task, so every task the requests touch is already closed. One run addresses every open request and publishes: a partial run leaves the same `# Due Next` line for the next pass, which the loop reads as no progress.

## Map each request to a task

```bash
pdlc inspect changes WORK_ITEM
```

Split every open request into findings:

- **Review findings** and **Verification bounce**: each finding is a fix.
- **Decision resolution**: apply each recorded answer to the tasks it affects; a deferred point stays out of scope.
- **CI failure**: diagnose it with [`fix-ci.md`](fix-ci.md), which returns each code cause as a finding with its owning task.

Skip a finding the current source already addresses, such as one a re-implemented task fixed, and note it for the evidence. A finding that changes approved intent follows Requirement corrections.

Give each remaining finding an owning task by the first rule that applies:

1. It names a task id: that task.
2. It names files, and one task's PR touched them: that task. `pdlc inspect test WORK_ITEM` lists every closed task with its PRs and the files they touched.
3. It spans several tasks' files, or only new files: it is **cross-cutting**, owned by the top task, the last branch `gh stack view` lists. That branch already holds every task's code.
4. The change it asks for is unclear: report it to the driver with the request's link, and stop.

This step is complete when every finding has an owning task, or an unclear one has stopped the run.

## Fix each task, lowest first

Work through the owning tasks in stack order, lowest first: re-landing a task rebases every branch above it. For each task:

1. **Branch.** With the tree clean, as in Implement, run `pdlc checkout DELIVERY_TASK`.
2. **Dispatch** the task's `## Agent` implementer, from `pdlc inspect task DELIVERY_TASK`, with [`task-implementation-prompt.md`](task-implementation-prompt.md). The Gate evidence is this task's findings verbatim; a cross-cutting finding also says it spans tasks and names the files. The fix is one new commit on top.
3. **Validate** as in Implement.
4. **Review** the fix commit at task depth, as in Review.
5. **Re-land** the task without `--close`; it stays closed:

   ```bash
   pdlc post implement-task DELIVERY_TASK /tmp/pdlc-task-summary.md
   ```

   Write the summary as the task's whole implementation, starting from its current `## Implementation` in `pdlc inspect task DELIVERY_TASK`, plus one line per finding this fix addresses: re-landing replaces that comment and the PR description. On the top task, give each cross-cutting fix its own line naming its finding, so the PR's reviewers see why code outside the task is there.

This step is complete when every owning task has a reviewed fix commit on its branch, and its re-land JSON shows its `taskPr`.

## Publish

When a CI failure was among the requests, first watch every PR that was red to a result (`gh pr checks PR --watch`). Publish only when all of them are green; a red check is another diagnosis through [`fix-ci.md`](fix-ci.md), and a third red on the same cause goes to the driver.

Run Publish with evidence naming each open request and how it was addressed: the owning task and fix commit, already addressed by current source, or a green rerun. This path is complete when the JSON shows `gateState: Review Required`; the stage review runs again from there.
