---
id: "FILE-60"
content:
  number: 60
  title: "Record 60"
  url: "file://x/60"
Status: "Implementation"
Gate State: "Changes Required"
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
    checks: "FAILURE"
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

Due next: Implementation.ChangesRequired → triage live pull-request signals.
Invoke the `pdlc-triage` skill for this work item.

### CI failures

- PR #40: FAILURE (u40)

Read `pdlc guide triage-ci-failure` and investigate these failed checks.

Triage every signal, then use `pdlc post triage 60 TARGET EVIDENCE_FILE` to route an actionable change to Implementation or Testing. Follow the owning stage's normal pipeline from Changes Required. A decision needing the driver stops here.
