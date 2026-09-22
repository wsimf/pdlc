## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Technical Plan"
Gate State: "Decision Required"
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

Due next: TechnicalPlan.DecisionRequired → This work item is pending user decision.
Inspect the evidence section below, inform the user of the decision required, and record their
choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about
arguments to pass. Call `pdlc guide decisions` for information about how to handle user
decision recording.

### Evidence

This evidence was posted at 2026-03-01 00:00 UTC.
## Decision Required

On-device vs server-side snapping?

Call `pdlc inspect timeline 60` for the full timeline context of this work item.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'Technical Plan', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Decision Required' — a prior review raised a blocking finding the driver must resolve (see last the PDLC-DECISION comment) before review can resume.

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
- [gate] Gate State is 'Decision Required', not Approval Required. Verification is unfinished.
- [open-tasks] Open delivery tasks must leave active scope through a durable defer or descope before completion: #601 WORK-60-TASK-001 [CORE] Core work, #602 WORK-60-TASK-002 [UI] Second
- [closed-without-implementation] Closed tasks with no implementation pull request attached: #603
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
