## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Product"
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

No Tasks

# Due Next

Due next: Product.ChangesRequired → This work item needs changes.
User has requested changes. Inspect the open changes below. If the required changes are clear,
invoke pdlc-write and continue to write the product content. If not, ask the user
what changes are needed. Provide context to the user about this work item, since they might
not understand what we are working on.

### Open Changes

1 open change request for Product: Review findings.
Run `pdlc inspect changes 60` for their full text, and address every one of them.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'Product', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Changes Required', not Review Required.

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
- [gate] Gate State is 'Changes Required', not Approval Required. Verification is unfinished.
- [stage-evidence] No stage evidence comment on record for: Product, UI, Tasks, Technical Plan, Implementation, Testing
- [stage-settlement] Each non-skipped stage needs one settlement marker (PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); found 0, expected at least 6.
- [no-verification] No Verification review evidence — pdlc-verify must run first.

## Attachments

None
