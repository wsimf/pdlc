## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Verification"
Gate State: "Decision Required"
Lifecycle: "Planning"
workType: "feature"
Skipped States: ""
pullRequests:
  - number: 40
    title: "t"
    url: "u40"
    state: "MERGED"
    isDraft: false
    branch: "b"
    mergedAt: "2026-01-02T00:00:00Z"
    checks: "SUCCESS"
  - number: 41
    title: "t"
    url: "u41"
    state: "MERGED"
    isDraft: false
    branch: "b"
    mergedAt: "2026-01-02T00:00:00Z"
    checks: "SUCCESS"
---

# Work Item

## Product

### 4. Functional requirements
- FR-1: The record lands.

## UI

### UJ-1: First run

- Entry: cold launch
- Flow: the app opens to the map
- Criteria: the map is interactive within 2s

## Decisions
- none

## Open Questions
- Q-1: Should the cache survive a relaunch?

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

Due next: Verification.DecisionRequired → This work item is pending user decision.
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

Not ready: Status is 'Verification', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Decision Required' — a prior review raised a blocking finding the driver must resolve (see last the PDLC-DECISION comment) before review can resume.

## Attachments

None

## $ pdlc inspect test 60

## Readiness

Not ready: Status is 'Verification', not Testing. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect verify 60

## Readiness

Not ready: parked at Decision Required — a finding needs a driver call. The driver clears it via `pdlc guide decisions` (pdlc post decision), which returns it to Changes Required for a re-verify.

## Attachments

None

## $ pdlc inspect complete 60

## Readiness

Not ready — resolve each of these before completing:

- [gate] Gate State is 'Decision Required', not Approval Required. Verification is unfinished.
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
