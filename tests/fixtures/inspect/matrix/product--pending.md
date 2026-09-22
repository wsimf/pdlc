## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Product"
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

No Tasks

# Due Next

Due next: Product.Pending → This work item is pending user input.
Invoke pdlc-write skill interactively.
Product artifact is due; user must invoke pdlc-write interactively,
and it is not possible to continue autonomously.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'Product', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Pending', not Review Required.

## Attachments

None

## $ pdlc inspect test 60

## Readiness

Not ready: Status is 'Product', not Testing. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect verify 60

## Readiness

Not ready: Status is 'Product', not Verification. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect complete 60

## Readiness

Not ready — resolve each of these before completing:

- [status] Status is 'Product', not Verification. That stage owns this record now.
- [gate] Gate State is 'Pending', not Approval Required. Verification is unfinished.
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
