## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Technical Plan"
Gate State: "Approved"
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

# Warnings

The Gate State claims more than this work item's evidence shows. `# Due Next` still routes on the gate;
report each warning to the driver rather than working around it.

- Technical Plan is at a stray Approved its evidence does not support (no PDLC-PLAN publication of Technical Plan is on record); it heals to Technical Plan / Approval Required, not the next stage.

# Due Next

Due next: TechnicalPlan.Approved → This work item has been approved to continue.
Call `pdlc next 60` to continue this work item.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'Technical Plan', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Approved', not Review Required.

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

exit 1

pdlc: active stage cannot remain Approved: Technical Plan
