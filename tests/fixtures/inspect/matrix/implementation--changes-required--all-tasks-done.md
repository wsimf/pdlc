## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Implementation"
Gate State: "Changes Required"
Lifecycle: "Planning"
workType: "feature"
Skipped States: ""
pullRequests:
  - number: 40
    title: "t"
    url: "u40"
    state: "OPEN"
    isDraft: false
    branch: "b"
    mergedAt: null
    checks: "SUCCESS"
  - number: 41
    title: "t"
    url: "u41"
    state: "OPEN"
    isDraft: false
    branch: "b"
    mergedAt: null
    checks: "SUCCESS"
---

# Work Item

## Product

### 4. Functional requirements
- FR-1: The record lands.
- FR-2: The record publishes.

### 5. Constraints
- C-1: Commands own every mutation.

## UI

UJ-1 covers the first run.

## Decisions
- none

## Open Questions
- none

## Attachments

None

## User Comments

None

# Tasks

---
number: 601
title: "WORK-60-TASK-001 [CORE] First"
completed: true
isUI: false
hasPlan: true
hasImplementation: true
implementationInvalidated: false
needsPlan: false
---

---
number: 602
title: "WORK-60-TASK-002 [UI] Second"
completed: true
isUI: true
hasPlan: true
hasImplementation: true
implementationInvalidated: false
needsPlan: false
---

# Due Next

Due next: Implementation.ChangesRequired → This work item needs changes.
User has requested changes. Inspect the open changes below. If the required changes are clear,
invoke pdlc-implement and continue implementing the next eligible delivery task. If not, ask
the user what changes are needed. Provide context to the user about this work item, since they might
not understand what we are working on.

### Next Pending Task

No delivery tasks are currently pending implementation.

### Open Changes

1 open change request for Implementation: Review findings.
Run `pdlc inspect changes 60` for their full text, and address every one of them.

## $ pdlc inspect implement 60

## Readiness

Ready — Gate State: Changes Required.

## Mode

mode: triage

## Attachments

None

## Open Requests

Every delivery task is already implemented and published in the PR stack below; these requests ask for changes to that implemented work. Run `pdlc checkout NUMBER` with the top task's number to put the working tree on the top branch with every task branch of the stack local. Each fix lands as a new commit on the branch of the task it belongs to, lowest first; a fix with no clear owner, or one that needs a lower fix to build on, goes on the top branch. These requests stay listed until the stage publishes, so this unit is offered again until then.

### Review findings

<review-finding date="2026-03-01 00:00 UTC" url="file://x#c">
#### Findings

- Tighten section 2.
</review-finding>

#### Stack
- WORK-60-TASK-001 [CORE] First (number 601, PR #40)
- WORK-60-TASK-002 [UI] Second (number 602, PR #41, top)

Next: Run `pdlc inspect task NUMBER` for each task in the stack for its technical plan, and for the top task's implementer sub-agent under `## Agent`; then dispatch that sub-agent once with every request above and the stack, to place and fix each finding on its owning task's branch.

## Publish

After every fix is committed on its task branch, run `pdlc post implement 60 EVIDENCE` from the top branch to push the whole stack and publish the stage; the evidence names how each request was addressed.

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Changes Required', not Review Required.

## Attachments

None

## $ pdlc inspect test 60

## Readiness

Not ready: Status is 'Implementation', not Testing. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect verify 60

## Readiness

Not ready: Status is 'Implementation', not Verification. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect complete 60

## Readiness

Not ready — resolve each of these before completing:

- [status] Status is 'Implementation', not Verification. That stage owns this record now.
- [gate] Gate State is 'Changes Required', not Approval Required. Verification is unfinished.
- [pull-requests] Every linked closing PR must be merged with passing required checks, or explicitly unlinked: #40 OPEN checks:SUCCESS, #41 OPEN checks:SUCCESS
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
