## Objective

You are resolving the unresolved review comments on pull request `40` in `acme/widgets`. Its branch is already checked out and holds the implementation the comments are about. Investigate the current implementation thoroughly before changing anything: read the code each comment names, its callers, and its tests, so each comment is judged against what the code does now, not against the diff alone. Then triage the comments and implement.

## Task

`WORK-60-TASK-001` (tag included) — `[CORE] First`

## Scope
x

## Acceptance criteria
- ok

## Technical Plan

Touch one module.

## Decisions

No previously recorded decisions.

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
  }' -f owner='acme' -f repo='widgets' -F pr=40

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

## Fixing a finding

Fix the cause, not the symptom. A symptom fix leaves the real defect in place
and makes the next one harder to find.

- Reproduce the failure before you change anything, so you can tell a fix from
  a coincidence.
- Ask why the failure happens until the answer is a line of code, not a
  condition you can guard against.
- A guard that only silences the symptom is not a fix: a nil check that stops a
  crash, a retry around a call that should not fail, a catch that swallows the
  error, a default that hides a missing value.
- If a fix needs a paragraph of comment to justify it, the code is wrong. Fix
  the code (not the comment).
- Fix the pattern, not the instance: search the files this fix owns for the
  same shape and fix every one you find there. Report the ones outside those
  files rather than widening the change.
- When a failure follows a restart, a rerun, or a fresh checkout, suspect stale
  state before code — caches, lock files, serialised state, generated output.
- When you are stuck, instrument. Add logging, read the actual error, print the
  real value. Do not guess at the cause.

**Two failed fixes at the same gate stop the loop.** When a second fix fails the
same check, the premise both fixes shared is the suspect, not the fixes. Do not
write a third. Write that premise down in one sentence, and report it with what
each attempt changed and how each failed. That is a decision for a human, not a
retry.

## Shape of the change

Make the smallest change that satisfies the task, and leave the code you touch
simpler than you found it. Removals stay inside the files this task owns —
anything wider is a line in your report, not a change.

- Subtract before you add. Dead code, a stub, a redundant validator, or a
  decision duplicated across the files you are touching goes first; build on
  the smaller base.
- Fewer lines beat elegant boilerplate. A wrapper, layer, or abstraction with
  one caller is not worth its indirection.
- Do not repeat a decision in several places. Put it behind one source of truth
  and pass the result.
- Do not thread a new signal through types, schemas, or pipelines when a direct
  path exists. Where the plan asks for the threading, follow the plan and say
  in your report where the direct path would have done.
- When this task replaces an internal API, migrate its callers and delete the
  old one here. A compatibility shim kept only because internal callers still
  exist is dual-path complexity, not a migration.
- If answering a question about this code takes tracing through more than about
  three files, the shape is wrong.

Types and boundaries:

- Make illegal states unrepresentable. Model variants as a sum type rather than
  a bag of optional fields whose contradictory combinations still compile. If
  you could write a comment explaining which combinations are valid, the type
  is too loose.
- Give distinct meanings distinct types. Two parameters that share a primitive
  type and mean different things should not be interchangeable.
- Parse external data at the boundary — CLI arguments, config, network
  payloads, stored rows — into the typed model, then trust the types inside. A
  nil check deep in a call chain the boundary already covered is noise.
- Do not lie to the compiler. A cast, force-unwrap, or assertion that bypasses
  a fact you cannot prove is a runtime failure in waiting: prove it, model it
  away, or report that you could not.
- Match on a variant exhaustively, so a variant added later fails the build
  instead of falling through silently.

## Code comments

Write a comment only where the code cannot say it itself. Clear code needs no
comment, and a rename or a smaller function beats a line of English explaining
a confusing one.

A comment never carries the work. It names no work item, delivery task,
requirement, journey, pull request, or branch, and it repeats no scope,
non-goal, or acceptance criterion from the task. A tag like
`WORK-12-TASK-003`, a reference to `FR-4`, or a line reading "added for the
auth task" sends the next reader to a record instead of the code, and goes
stale as soon as the code moves.

A comment describes the code as it stands today, never the change that
produced it. Drop "new", "now handles", "updated to", and "previously"; the
diff and the history own that story.

What earns a comment:

- A decision the code cannot show: why this approach rather than the obvious
  one, or what breaks if the order changes.
- A contract or ownership boundary: what a caller may assume, and what this
  code refuses to do.
- A constraint imposed from outside: a platform bug worked around, a call that
  must happen on a particular thread, a limit the API sets.

What does not:

- A restatement of the line below it.
- A name the code should carry instead. Rename the symbol.
- A TODO pointing at work nobody has agreed to. Report it instead.

Keep every comment you touch true. A comment that no longer matches the code
costs the reader more than no comment at all.

## Failing checks

- PR #40: FAILURE (u40)
