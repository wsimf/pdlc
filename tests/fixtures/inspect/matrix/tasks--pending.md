## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Tasks"
Gate State: "Pending"
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
hasPlan: false
hasImplementation: false
implementationInvalidated: false
needsPlan: true
---

# Due Next

Due next: Tasks.Pending → This work item is due for the Tasks stage.
Invoke pdlc-tasks skill autonomously.
UI or task artifact is due; the driver may invoke pdlc-tasks directly,
and it is possible to continue autonomously.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'Tasks', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Pending', not Review Required.

## Attachments

None

## $ pdlc inspect test 60

## Readiness

Not ready: Status is 'Tasks', not Testing. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect verify 60

## Readiness

Not ready: Status is 'Tasks', not Verification. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect complete 60

## Readiness

Not ready — resolve each of these before completing:

- [status] Status is 'Tasks', not Verification. That stage owns this record now.
- [gate] Gate State is 'Pending', not Approval Required. Verification is unfinished.
- [open-tasks] Open delivery tasks must leave active scope through a durable defer or descope before completion: #601 WORK-60-TASK-001 [CORE] Core work
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
