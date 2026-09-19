# Triage dispatch prompt

`pdlc-implement` Triage fills the placeholders below and spawns exactly one
implementer sub-agent with the result — the one named under `## Agent` by
`pdlc inspect task` for the top task in the stack (`general-purpose` when the
project configures no implementer). One dispatch per triage pass, after the
skill has run `pdlc checkout` for the top task so every task branch of the
stack is local and the top branch is checked out.

Paste every request from the unit's `## Open Requests` verbatim under
`## Requests`. Fill `## Stack` from `#### Stack` and `pdlc inspect task` for
each task: its branch, its title, and its `## Technical Plan`, lowest first.

The agent knows nothing about the PDLC pipeline: it sees review findings, a set
of branches, and the working tree. Tell it nothing about stages, gates, or the
parent work item. It commits but never pushes, rebases, or amends — the stack
and its pull requests stay with the skill and the CLI, which publishes every
branch at once when the pass lands.

---

```md
## Objective

The branches below are a stack of pull requests that together implement one
feature, lowest first; each higher branch builds on the one beneath it. A
reviewer has asked for changes to that implemented work. Investigate the
current implementation thoroughly before changing anything: read the code each
request names, its callers, and its tests, on the branch that owns it. Then
place each finding on the branch of the task it belongs to and fix it there.

## Requests

<every open change request, verbatim, each under its own heading>

## Stack

<lowest first, one entry per task:>

### <branch> — `<WORK-NNN-TASK-NNN>` `<title>`

<the task's `## Technical Plan`, verbatim>

<... the last entry is the top branch, which is currently checked out>

## Execution boundary

You are being invoked as a leaf worker for this one set of requests.
Do not invoke any `pdlc-*` skill.
Do not spawn, dispatch, or ask another agent to do this work.
Switch only between the branches listed under `## Stack`, with `git checkout`;
do not create, rename, rebase, or merge a branch, and do not push.

## Workflow

1. **Split** each request into findings: one concrete change each.
2. **Place** each finding on the branch of the task whose plan owns the code it
   changes. When no task clearly owns it, when it spans tasks, when it only
   adds new files, or when its fix needs a fix you are making on a lower
   branch, place it on the top branch instead. A higher branch does not
   contain what you commit on a lower one until the stack is later rebased.
3. **Fix** lowest branch first: check out the branch, implement the finding,
   verify with the relevant project command, and commit there with a message
   naming the request it answers. Never amend, rebase, or squash existing
   commits. Then move up.
4. A finding the current code already meets needs no change; note it with the
   evidence.
5. Stop and report, without committing anything for it, when a finding
   requires a product, architecture, UX, safety, or scope decision, or when
   fixing it would change what a task was specified to do.
6. Finish on the top branch, with a clean tree on every branch you touched.

## Report back

One entry per finding: the request it came from, the disposition (fixed,
already met, or needs a decision), the branch and commit for a fix or the
evidence for an already-met one, and one sentence on why it belongs on that
branch. Then the validation actually run, and any point where a plan did not
fit the code. Do not repeat the requests.
```
