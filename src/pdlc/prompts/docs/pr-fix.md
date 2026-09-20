## Objective

You are resolving the unresolved review comments on pull request `{{PR_NUMBER}}` in `{{OWNER}}/{{REPO}}`. Its branch is already checked out and holds the implementation the comments are about. Investigate the current implementation thoroughly before changing anything: read the code each comment names, its callers, and its tests, so each comment is judged against what the code does now, not against the diff alone. Then triage the comments and implement.

{{INCLUDE:shared/task.md}}

## Technical Plan

{{TECHNICAL_PLAN}}

## Decisions

{{DECISIONS_TEXT}}

{{INCLUDE:shared/execution-boundary.md}}
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
  }' -f owner='{{OWNER}}' -f repo='{{REPO}}' -F pr={{PR_NUMBER}}

The GraphQL query must fetch reviewThreads, isResolved, path, line, thread id,
and comments.

Triage rules:
- Iterate through ALL review threads in the PR and filter isResolved: false.
- Read every comment in each unresolved thread.
- Browse code at path around line; expand to helpers, callers, tests, or docs
  when needed.
- Treat a comment as **valid** only when the current code still has the issue
  or the requested change is required by project standards, and the fix stays
  inside the Technical Plan and acceptance criteria above.
- Treat a comment as **invalid** when the code already handles it, the
  suggestion no longer matches the current diff, it would regress behavior, or
  it conflicts with explicit project conventions.
- Treat a comment as **out of scope** when doing what it asks would change the
  Technical Plan's file ownership, interfaces, or approach, or an acceptance
  criterion above.
- **Approved**: a thread named under `## Decisions` above that is still
  unresolved has been reviewed by a human and approved for implementation.
  Treat it as valid whatever the rules above say, and follow the answer's
  wording where it gives one. "No previously recorded decisions." means no
  thread is approved this way.

Only a valid or approved comment is acted on. An invalid or out-of-scope
comment is skipped: do not fix it, do not reply, do not resolve it, and do not
touch the thread in any way; a human decides it later. Note the thread, what it
asks, and why you judged it invalid or out of scope for the report.

For each valid or approved item note down:
thread id, path, line, reviewer request, why it applies, concrete fix needed,
and suggested verification.

### 2. Implementation
For each valid or approved item returned by the above step:
1. Implement the requested change surgically.
2. Add or update focused tests when the risk justifies it.
3. Verify with the relevant project command.
4. Post a Github reply such as `Fixed in <summary>` and resolve the thread.

### 3. Finalization
Once **ALL** unresolved comments have been processed:
1. Commit everything with a meaningful summary of the changes; leave nothing uncommitted.
2. Do not attempt to push any code.
3. Report every thread and its disposition, plus the commits and the validation actually run:
   - fixed, with the change;
   - **skipped**, one entry per thread, with the thread's link, what the reviewer asks for in one sentence, whether you judged it invalid or out of scope, and why — naming the code that already handles it, or the plan or criterion it diverges from.

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
- **Skipped means untouched**: no reply, no resolve, no reaction on a skipped
  thread; it is handed to a human as it stands.
- **Verification**: Run the relevant project test/build command before resolving
  fixed threads.
- **Communication**: Keep GitHub replies concise, technical, and thread-specific.

{{INCLUDE:shared/code-comments.md}}
{{#IF FAILING_CHECKS}}

## Failing checks

{{FAILING_CHECKS_TEXT}}
{{/IF}}
