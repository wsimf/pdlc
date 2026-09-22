## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Testing"
Gate State: "CI Pending"
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

# Warnings

The Gate State claims more than this work item's evidence shows. `# Due Next` still routes on the gate;
report each warning to the driver rather than working around it.

- Testing is at CI Pending, but its evidence shows no clean result for CI to settle: no PDLC-TESTING publication of Testing is on record.

# Due Next

Due next: Testing.CIPending → This work item is pending CI build.
Call `pdlc post ci 60 --wait` to monitor and resolve the CI gates; do not use internal gh cli directly as it doesn't configure the pdlc state after CI failure. Act on the instructions provided by that command.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'Testing', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'CI Pending' — the stage's review (or Verification's clean run) already passed; the record is waiting on the registered PR stack's CI. pdlc post ci resolves it once checks finish (see `pdlc guide resolve-ci`).

## Attachments

None

## $ pdlc inspect test 60

## Readiness

Not ready: Gate State is 'CI Pending'. The testing review passed; the registered pr stack's ci outcome must be recorded.

## Attachments

None

## $ pdlc inspect verify 60

## Readiness

Not ready: Status is 'Testing', not Verification. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect complete 60

## Readiness

Not ready — resolve each of these before completing:

- [status] Status is 'Testing', not Verification. That stage owns this record now.
- [gate] Gate State is 'CI Pending', not Approval Required. Verification is unfinished.
- [pull-requests] Every linked closing PR must be merged with passing required checks, or explicitly unlinked: #40 OPEN checks:SUCCESS, #41 OPEN checks:SUCCESS
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
