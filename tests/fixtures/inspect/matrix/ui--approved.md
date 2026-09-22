## $ pdlc inspect 60 --full

---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "UI"
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

No Tasks

# Warnings

The Gate State claims more than this work item's evidence shows. `# Due Next` still routes on the gate;
report each warning to the driver rather than working around it.

- UI is at a stray Approved its evidence does not support (no PDLC-UI publication of UI is on record); it heals to UI / Approval Required, not the next stage.

# Due Next

Due next: UI.Approved → This work item has been approved to continue.
Call `pdlc next 60` to continue this work item.

## $ pdlc inspect implement 60

## Readiness

Not ready: Status is 'UI', not Implementation. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect review 60

## Readiness

Not ready: Gate State is 'Approved', not Review Required.

## Attachments

None

## $ pdlc inspect test 60

## Readiness

Not ready: Status is 'UI', not Testing. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect verify 60

## Readiness

Not ready: Status is 'UI', not Verification. That stage owns this Work Item now.

## Attachments

None

## $ pdlc inspect complete 60

exit 1

pdlc: active stage cannot remain Approved: UI
