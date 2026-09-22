## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Verification"
Gate State: "Review Required"
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

Due next: Verification.ReviewRequired → This stage does not require any additional reviewing.
Call `pdlc next 60` to continue this work item.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'Verification', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Verification never reaches Review Required — something published without going through its owning skill's local review.

## Attachments

None

## $ pdlc inspect test 60

## Readiness

Not ready: Status is 'Verification', not Testing. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect verify 60

## Readiness

Not ready: malformed Gate State 'Review Required'.

## Attachments

None

## $ pdlc inspect complete 60

exit 1

pdlc: stage does not support persisted independent review: Verification
