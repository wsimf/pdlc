# Uncommitted changes

`pdlc checkout` refuses to leave a branch while the working tree holds uncommitted changes. Decide whose work they are before running it again.

## Decide

Run `git status --short`, then `pdlc inspect task DELIVERY_TASK` for the task you are about to check out. The changes belong to that task when the files they touch are ones its `## Technical Plan` owns. Otherwise they belong elsewhere, or you cannot tell; treat both the same.

## They belong to this task

```bash
pdlc checkout DELIVERY_TASK --carry-changes
```

The changes come along onto the task's branch, and the task's implementer brief tells its agent to continue from them. If they conflict with that branch, the command says so and keeps them in a stash; resolve the conflicts in the tree, then drop that stash.

## They do not belong to this task

Set them aside in a stash named for the task you are about to check out and the branch they were found on, then check out:

```bash
git stash push --include-untracked -m "pdlc: set aside before WORK-142-TASK-004; found on pdlc/record-142/task-003"
pdlc checkout WORK-142-TASK-004
```

Name the stash in your report. Nothing is lost: `git stash list` shows it, and `git stash pop stash@{N}` restores it.

## After an agent returns

The same applies when an agent reports back and the tree still holds changes it did not commit: they are not that agent's work, so set them aside as above and name the stash in your report.
