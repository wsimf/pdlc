# Fix PR Comments Procedure

Sends the block below to the task's implementer sub-agent, one dispatch per pull request with unresolved review threads, after checking out that task's branch. Fill `<PR_NUMBER>`, `OWNER`, and `REPO` from the PR the dispatch covers; the agent triages the live threads itself, so the skill does not paste the comment bodies in.

The agent knows nothing about the PDLC pipeline: it sees one PR, its open threads, and the working tree. Tell it nothing about stages, gates, or the parent work item. It commits but never pushes — the branch, the re-land, and the stage evidence stay with the skill.

Per PR, lowest in the stack first, since re-landing a task rebases every branch above it:

1. **Map** the PR to its delivery task. `pdlc inspect test WORK_ITEM` lists every closed task with its linked PRs; `pdlc inspect implement WORK_ITEM` names an open one.
2. **Branch.** With the tree clean, `pdlc checkout DELIVERY_TASK`.
3. **Dispatch** that task's `## Agent` implementer, from `pdlc inspect task DELIVERY_TASK`, with the block below.
4. **Validate** the returned commit as in Implement, and review it at task depth as in Review.
5. **Re-land** as in Land, omitting `--close` when the task is already closed, with a summary naming each thread the fix addressed.

A comment that turns on a product, architecture, UX, safety, or scope call is not this skill's to settle: report it to the driver with the thread's link and stop, leaving the thread open. A comment asking for a change to approved intent follows Requirement corrections. Publish once every PR's threads are resolved or reported; evidence names each PR, its fix commit, and any thread left open with why.

```md
## Quick start

You are resolving the unresolved review comments on pull request `<PR_NUMBER>` in `OWNER/REPO`. Its branch is already checked out. Triage and explore the comments, then implement.

## Execution boundary

You are being invoked as a leaf worker for this one pull request.
Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Do not create, switch, or rename a branch, and do not push.

## Workflows

### 1. Triage Comments

Find all unresolved review threads on the current PR with gh:

gh pr view --json number,repository
gh api graphql -f query='
  query($owner:String!, $repo:String!, $pr:Int!) {
    repository(owner:$owner, name:$repo) {
      pullRequest(number:$pr) {
        reviewThreads(first: 50) {
          nodes {
            id
            isResolved
            path
            line
            comments(first: 20) {
              nodes {
                body
                author { login }
              }
            }
          }
        }
      }
    }
  }' -f owner='OWNER' -f repo='REPO' -F pr=PR_NUMBER

The GraphQL query must fetch reviewThreads, isResolved, path, line, thread id,
and comments.

Triage rules:
- Iterate through ALL review threads in the PR and filter isResolved: false.
- Read every comment in each unresolved thread.
- Browse code at path around line; expand to helpers, callers, tests, or docs
  when needed.
- Treat a comment as valid only when the current code still has the issue or the
  requested change is required by project standards.
- Treat a comment as invalid when the code already handles it, the suggestion no
  longer matches the current diff, it would regress behavior, or it conflicts
  with explicit project conventions.

If a comment is invalid, obsolete, already addressed, or not required by the current code, post a concise GitHub thread reply explaining why no fix is needed. Resolve those threads as well.

For each item note down:
thread id, path, line, reviewer request, why it is valid, concrete fix needed,
and suggested verification.

### 2. Implementation
For each valid item returned by the above step:
1. Implement the requested change surgically.
2. Add or update focused tests when the risk justifies it.
3. Verify with the relevant project command.
4. Post a Github reply such as `Fixed in <summary>` and resolve the thread.

### 3. Finalization
Once **ALL** unresolved comments have been processed:
1. Commit with a meaningful summary of the changes.
2. Do not attempt to push any code.
3. Report every thread and its disposition: fixed (with the change), replied as not needed (with the reason), or left open (with why), plus the commit and the validation actually run.

### 4. GitHub Actions

#### Reply to a Thread
Use this to provide justification or ask for clarification on GitHub.
```bash
gh api graphql -f query='
  mutation($threadId: ID!, $body: String!) {
    addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
      comment { id url }
    }
  }' -f threadId="THREAD_ID" -f body="Your justification or question here"
```

#### Resolve a Thread
Use this after implementing a fix.
```bash
gh api graphql -f query='
  mutation($id: ID!) {
    resolveReviewThread(input: {threadId: $id}) {
      thread { id isResolved }
    }
  }' -f id='THREAD_ID'
```

## Guidelines
- **Context first**: Do not edit until unresolved threads have been triaged.
- **Verification**: Run the relevant project test/build command before resolving
  fixed threads.
- **Communication**: Keep GitHub replies concise, technical, and thread-specific.
```