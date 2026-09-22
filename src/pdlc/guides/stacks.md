# Stacked pull requests

Use this guide when a delivery task's branch, its pull request, or the stack they belong to is not where `pdlc` expects it. It explains what `pdlc` runs behind each command and how to put a stack back so the next command succeeds.

## The model

Each delivery task gets one branch, and each branch gets one pull request. Each PR is based on the branch of the task implemented before it:

```
(main) <- pdlc/record-142/task-001 <- pdlc/record-142/task-002 <- pdlc/record-142/task-003
```

Left is the bottom and merges first. Right is the top.

Ownership is split three ways, and no party re-derives another's state:

| Owner | Owns | Read it with |
| --- | --- | --- |
| `gh stack` (the `github/gh-stack` extension) | stack order, PR bases, rebases, which branches have merged | `gh stack view --json` |
| The record | which PRs belong to the work item: the numbers registered on the record and its delivery tasks | `pdlc inspect <WORK_ITEM>` |
| `pdlc` | the branch name `pdlc/<slug>/<task-id>` | `pdlc inspect implement <WORK_ITEM>` |

`pdlc` never infers a PR from a branch name, a remote branch listing, or a `Closes #N` keyword. It only uses a registered PR number. When the stack and the record disagree, fix the side that is wrong, and do not work around it.

## What each command runs

| `pdlc` command | Behind the scenes |
| --- | --- |
| `pdlc inspect implement` | Read-only. Names the next task and its `branch:`. |
| `pdlc checkout <WORK-N-TASK-NNN>` | Refuses a dirty tree. If the task has a registered PR, it runs `gh stack checkout <pr>`. If only a local branch exists, it runs `gh stack checkout <branch>`. If an earlier task has a PR, it runs `gh stack checkout <entry-pr>` and then `gh stack add <branch>`. If the current branch is already on a stack, it runs `gh stack top` and then `gh stack add <branch>`. Otherwise it runs `gh stack init <branch>`. |
| `pdlc post implement-task` | Runs `gh stack rebase --no-trunk` and then `gh stack submit --auto`, so new trunk commits never enter the stack. When a stack PR has merged on GitHub and its branch is still local, it runs `gh stack sync --prune` in place of the rebase, which rebases onto trunk and drops the merged branch. It picks the submitted PR whose head is this task's branch, overwrites that PR's title and body with `gh pr edit`, and registers the PR number on the task. |
| `pdlc post implement` | Runs the same restack and submit, then `gh pr ready` on every registered open PR. |
| `pdlc post test` | Runs the same restack and submit from the top task branch, then registers the current branch's PR (`gh pr view`) on the record. |
| `pdlc post ci` | Reads the check rollup of every registered PR. Any red PR makes the result red. Any pending PR makes it pending. |
| `pdlc post complete` | After locking, force-deletes each merged PR's local branch, but only when the branch tip still equals the PR's head commit. |

## Rules that keep the stack sound

- Create and switch task branches only through `pdlc checkout`. A branch made with `git checkout -b` is not on the stack, and submit will not find it.
- Never `git push` a task branch by hand. The `pdlc post` commands push the stack through `gh stack`, which keeps every base chained.
- Never change a PR's base with `gh pr edit --base`, and never merge with `gh pr merge`. Merging is a driver decision, made with `gh stack merge <top-pr> --yes`.
- Commit a fix on the branch of the task that owns it, then run `gh stack rebase --upstack` before returning to the top.
- Never run the interactive forms: bare `gh stack view`, `gh stack submit` without `--auto`, `gh stack switch`, or `gh stack modify`. Use `gh stack view --json` to read state.

## Diagnose

Start with these commands, and compare their output:

```bash
pdlc inspect <WORK_ITEM>          # registered PRs, their state and checks
pdlc inspect implement <WORK_ITEM> # next task and its branch
gh stack view --json              # local stack: branches, PRs, needsRebase, isMerged
git status && git branch --show-current
```

The stack is healthy when all of the following hold:

- Every delivery task that has an implementation appears in `gh stack view --json` as a branch named `pdlc/<slug>/<task-id>`.
- Each of those branches carries a `pr.number` that equals the number registered on its task.
- No branch reports `needsRebase: true`.

## Symptoms and fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `the gh stack extension is required` | The extension is not installed. | Run `gh extension install github/gh-stack`, then re-run the command. |
| `the submitted stack has no pull request for <branch> (branches submitted: …)` | The task branch is not on the stack that the current branch belongs to. Usually it was created with plain `git`, or the current checkout is on a different stack. | Run `gh stack view --json` and look for the branch. If the branch exists but is untracked, rebuild the stack so it adopts the branch: `gh stack unstack --local`, then `gh stack init --base <trunk> <task-001-branch> <task-002-branch> …` from bottom to top. Then re-run the `pdlc post` command. |
| `no pull request exists for the current branch` from `pdlc post test` | The current branch is not the top task branch. | Run `pdlc checkout <top task>` and re-run. |
| `pdlc post` fails with a rebase conflict (exit 3) | A change lower in the stack conflicts with a branch above it. `pdlc` has already restored every branch. | Run `gh stack rebase --no-trunk` to reproduce the conflict, or `gh stack sync --prune` if a stack PR has merged. Resolve the files and `git add` them, then run `gh stack rebase --continue` until it finishes. Re-run the `pdlc post` command. |
| `Sync aborted` on stderr, yet the command continued | The local stack and the stack on GitHub diverged. `sync` exits 0 and changes nothing. | To keep GitHub's version, run `gh stack unstack --local` and then `gh stack checkout <pr>`. To keep the local version, first note the branch order from `gh stack view --json`, because `gh stack unstack` removes both the GitHub grouping and local tracking. Then run `gh stack unstack`, `gh stack init --base <trunk> <task-001-branch> <task-002-branch> …` from bottom to top to adopt the existing branches, and `gh stack submit --auto` to re-link their PRs. Neither path deletes PRs or branches. Report to the driver if you cannot tell which version is right. |
| `gh stack checkout` refuses because another local stack covers those branches | Stale local tracking. | Run `gh stack unstack --local` (the stack on GitHub is kept), then re-run `pdlc checkout`. |
| Exit 6: the branch belongs to several stacks | The current branch is the trunk of more than one stack. | Check out a branch unique to the intended stack with `pdlc checkout <task>`. |
| Exit 8: the stack file is locked | Another `gh stack` process is writing. | Wait about 5 seconds and retry. |
| `working tree has uncommitted changes` from `pdlc checkout` | The tree is dirty. | Commit the change on the branch that owns it, or stash it. `pdlc` never forces a switch. |
| `registered pull request #N could not be found` | The record lists a PR number that the code host cannot resolve. This happens when the PR was deleted or the repository is wrong. | Check the output of `pdlc doctor`. If the number really is wrong, report it to the driver. `pdlc` has no command to remove a registered PR. |
| `pdlc post ci` holds `CI Pending` with no PR registered | Implementation and Testing publish through PRs, and none are registered. | Run `pdlc post attach-pr <delivery-task> <pr-number>`, then `pdlc post ci <WORK_ITEM>`. |
| A PR title or body shows `gh stack`'s generated text | The PR was created without a `pdlc post implement-task` run following it. `gh stack` writes the title and body only when it creates a PR. | Re-land the task with `pdlc post implement-task <task> <file>`. That run overwrites both fields. |
| A lower PR was squash-merged and the branches above look duplicated | Nothing is wrong. The next `pdlc post` sees the merged PR and runs `gh stack sync --prune`, which rebases onto trunk with `--onto` and skips the merged branch. | Let the next `pdlc post` run. `--prune` drops the merged branch locally. |
| `pdlc post complete` reports a branch as skipped with `sha-mismatch` | The local branch differs from the merged PR's head. It holds either unpushed commits or a rebase made after the merge. | Leave the branch alone. Deleting it could lose work, so report it to the driver. |

## Verification after a restack

Verification freshness compares file trees, not commit ancestry. A rebase or restack that leaves a task's files unchanged does not make its verification stale. A restack that changes those files does, and `pdlc inspect verify` reports it.

## Escalate

Stop and report to the driver when you cannot say which version of a diverged stack is correct, when a fix would rewrite a branch's history that has already been pushed and reviewed, or when the record's registered PRs do not match any branch in the stack. Include the output of `gh stack view --json` and `pdlc inspect <WORK_ITEM>`.
