# Fix PR comments prompt

`pdlc-implement` Implement sends the block below to the task's implementer sub-agent when the unit's `#### Unresolved threads` lists review threads, after checking out that task's branch. Fill `<PR_NUMBER>`, `OWNER`, and `REPO` from the unit's `pr:` line, and the `## Task` and `## Technical Plan` sections from `pdlc inspect task`, so the agent knows what the code was meant to do before it judges a comment; the agent triages the live threads itself, so the skill does not paste the thread bodies in. When the same unit also lists `#### Failing checks`, append the code causes from [`fix-ci.md`](fix-ci.md) under a `## Failing checks` heading at the end of the block. Fill `## Decisions` from the unit's `#### Decisions`, verbatim, or leave its "no previously recorded decisions" line when the unit has none; they are the driver's answers to threads escalated on an earlier pass, and a thread named there that is still open has been approved for implementation.

The agent knows nothing about the PDLC pipeline: it sees one PR, its open threads, and the working tree. Tell it nothing about stages, gates, or the parent work item. It commits but never pushes — the branch, the re-land, and the stage evidence stay with the skill.

A comment the agent judges invalid, or one that diverges from the agreed Technical Plan or acceptance criteria or turns on a product, architecture, UX, safety, or scope call, is not this skill's to settle. The agent skips it, leaves the thread untouched, and reports it back with its reasoning; the skill lands the other fixes, then escalates every skipped thread as a decision (see `SKILL.md` Escalate). The driver closes a thread that does not apply, or leaves it open to have it applied on the next pass.

```md
## Objective

You are resolving the unresolved review comments on pull request `<PR_NUMBER>` in `OWNER/REPO`. Its branch is already checked out and holds the implementation the comments are about. Investigate the current implementation thoroughly before implementing any fix: read the changed files, their callers, and their tests so each comment is judged against what the code does now, not against the diff alone. Then triage the comments and implement.

## Task

`<WORK-NNN-TASK-NNN>` (tag included) — `<title>`

<full task body: scope, non-goals, dependencies, FR/C/UJ coverage, acceptance
criteria — the contract the implementation on this branch was built to>

## Technical Plan

<the task's `## Technical Plan` comment, verbatim — the approach the
implementation follows; a fix stays inside it unless a comment shows it wrong>

## Decisions

<the unit's `#### Decisions` blocks, verbatim — each is a human's answer to a
review thread that was skipped on an earlier pass; a thread named here that is
still unresolved is approved for implementation — or the single line:
"No previously recorded decisions.">

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
```