## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Testing"
Gate State: "Stale"
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

Due next: Testing.Stale → This work item has been invalidated.
User has invalidated this work item's testing artifact. Invoke pdlc-test skill
and continue writing acceptance coverage for the required changes.
Inspect the open changes below to determine what changed. If they are not clear or if PDLC was
unable to provide them, stop and ask the user.

### Testable Scope

Call `pdlc inspect test 60` for the current testable scope: every delivery task closed
with its implementation recorded, its linked PRs, and the files those PRs touched.

### Open Changes

1 open change request for Testing: Invalidation.
Run `pdlc inspect changes 60` for their full text, and address every one of them.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'Testing', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Stale', not Review Required.

## Attachments

None

## $ pdlc inspect test 60

## Readiness

Ready — Gate State: Stale.

## Attachments

None

## Testable Scope

### WORK-60-TASK-001 [CORE] First

PR #40 (OPEN, checks: SUCCESS)
Files touched:
- src/a.py
- src/shared.py

### WORK-60-TASK-002 [UI] Second

PR #41 (OPEN, checks: SUCCESS)
Files touched:
- src/b.py
- src/shared.py

## Source

Testing at HEAD 0000000000000000000000000000000000000000 — every open task PR's head is included.

## $ pdlc inspect verify 60

## Readiness

Not ready: Status is 'Testing', not Verification. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect complete 60

## Readiness

Not ready — resolve each of these before completing:

- [status] Status is 'Testing', not Verification. That stage owns this record now.
- [gate] Gate State is 'Stale', not Approval Required. Verification is unfinished.
- [pull-requests] Every linked closing PR must be merged with passing required checks, or explicitly unlinked: #40 OPEN checks:SUCCESS, #41 OPEN checks:SUCCESS
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
