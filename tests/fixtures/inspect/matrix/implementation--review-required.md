## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Implementation"
Gate State: "Review Required"
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

# Warnings

The Gate State claims more than this work item's evidence shows. `# Due Next` still routes on the gate;
report each warning to the driver rather than working around it.

- Implementation is at Review Required, but no PDLC-IMPLEMENTATION publication of Implementation is on record, so there is nothing current to review.

# Due Next

Due next: Implementation.ReviewRequired → This work item is pending review.
Invoke pdlc-review skill with this work item's number. Pass the correct scope.
Default scope is every task delivered in the current publication pass;
if the user named a specific task or asked for a full audit, carry that scope into the
dispatch instead of the default.

## $ pdlc inspect implement 60

## Readiness

Not ready: Gate State is 'Review Required'. Review is due.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Ready — Status: Implementation, Gate State: Review Required.

## Attachments

None

## Reviewer Target

Artifact: Production PRs and each task's implementation
Reviewer agent: pdlc-implementation-reviewer

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
- [gate] Gate State is 'Review Required', not Approval Required. Verification is unfinished.
- [open-tasks] Open delivery tasks must leave active scope through a durable defer or descope before completion: #602 WORK-60-TASK-002 [UI] Second
- [pull-requests] Every linked closing PR must be merged with passing required checks, or explicitly unlinked: #40 OPEN checks:SUCCESS
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
