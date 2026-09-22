## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Technical Plan"
Gate State: "Changes Required"
Lifecycle: "Planning"
workType: "feature"
Skipped States: ""
pullRequests: []
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
completed: false
isUI: false
hasPlan: true
hasImplementation: false
implementationInvalidated: false
needsPlan: false
---

---
number: 602
title: "WORK-60-TASK-002 [UI] Second"
completed: false
isUI: true
hasPlan: false
hasImplementation: false
implementationInvalidated: false
needsPlan: true
---

---
number: 603
title: "WORK-60-TASK-003 [CORE] Done"
completed: true
isUI: false
hasPlan: true
hasImplementation: false
implementationInvalidated: false
needsPlan: false
---

# Due Next

Due next: TechnicalPlan.ChangesRequired → This work item needs changes.
User has requested changes. Inspect the open changes below. If the required changes are clear,
invoke pdlc-plan and continue to write the technical plan. If not, ask the user
what changes are needed. Provide context to the user about this work item, since they might
not understand what we are working on.

### Next Pending Task

The next task pending a Technical Plan is 602. Call `pdlc inspect task 602` for its current content, and `pdlc inspect task timeline 602` for its evidence history.

### Open Changes

1 open change request for Technical Plan: Review findings.
Run `pdlc inspect changes 60` for their full text, and address every one of them.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'Technical Plan', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Changes Required', not Review Required.

## Attachments

None

## $ pdlc inspect test 60

## Readiness

Not ready: Status is 'Technical Plan', not Testing. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect verify 60

## Readiness

Not ready: Status is 'Technical Plan', not Verification. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect complete 60

## Readiness

Not ready — resolve each of these before completing:

- [status] Status is 'Technical Plan', not Verification. That stage owns this record now.
- [gate] Gate State is 'Changes Required', not Approval Required. Verification is unfinished.
- [open-tasks] Open delivery tasks must leave active scope through a durable defer or descope before completion: #601 WORK-60-TASK-001 [CORE] Core work, #602 WORK-60-TASK-002 [UI] Second
- [closed-without-implementation] Closed tasks with no implementation pull request attached: #603
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
