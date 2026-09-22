## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Product"
Gate State: "CI Pending"
Lifecycle: "Planning"
workType: "feature"
Skipped States: ""
pullRequests:
  - number: 90
    title: "t"
    url: "u90"
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

No Tasks

# Warnings

The Gate State claims more than this work item's evidence shows. `# Due Next` still routes on the gate;
report each warning to the driver rather than working around it.

- Product is at CI Pending, but its evidence shows no clean result for CI to settle: no PDLC-PRODUCT publication of Product is on record.

# Due Next

Due next: Product.CIPending → We do not stop for CI at this stage.
Call `pdlc next 60` to continue this work item.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'Product', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'CI Pending' — the stage's review (or Verification's clean run) already passed; the record is waiting on the registered PR stack's CI. pdlc post ci resolves it once checks finish (see `pdlc guide resolve-ci`).

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

exit 1

pdlc: stage is not CI-gated: Product
