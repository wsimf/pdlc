## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Implementation"
Gate State: "Pending"
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
title: "WORK-60-TASK-001 [CORE] Core work"
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
completed: false
isUI: true
hasPlan: true
hasImplementation: false
implementationInvalidated: false
needsPlan: false
---

# Due Next

Due next: Implementation.Pending → This work item is due for the Implementation stage.
Invoke pdlc-implement skill and continue with instructions specified there.

### Next Pending Task

The next task pending implementation is 602. Call `pdlc inspect task 602` for its current content, and `pdlc inspect task timeline 602` for its evidence history.

## $ pdlc inspect implement 60

## Readiness

Ready — Gate State: Pending.

## Mode

mode: implement

## Attachments

None

## Implementation Notes

$CACHE_ROOT/.pdlc/cache/60/pdlc-implementation-notes.md

## Next Task

### WORK-60-TASK-002 [UI] Second
number: 602
taskId: TASK-002
isUI: true
branch: pdlc/record-60/task-002

Next: Run `pdlc inspect task 602` for the task body, acceptance criteria, technical plan, and the implementer sub-agent under `## Agent`, then `pdlc checkout 602` and dispatch that sub-agent to implement the task on the checked-out branch.

## Publish

After the task is implemented and its files are committed, run `pdlc post implement-task 602 SUMMARY` to record the implementation, open the task's PR, and close the task.

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Pending', not Review Required.

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
- [gate] Gate State is 'Pending', not Approval Required. Verification is unfinished.
- [open-tasks] Open delivery tasks must leave active scope through a durable defer or descope before completion: #602 WORK-60-TASK-002 [UI] Second
- [pull-requests] Every linked closing PR must be merged with passing required checks, or explicitly unlinked: #40 OPEN checks:SUCCESS
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
