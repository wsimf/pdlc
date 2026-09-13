# Due Next Section — Rendered Output Per Stage/Gate

The exact `# Due Next` section `pdlc inspect` renders for every `(Status, Gate State)` combination in the Feature pipeline, produced by calling `_due_next_section()` in `src/pdlc/commands/inspect.py` directly for each cell.

See `stage-ownership.md` for the underlying status/action/owner matrix; this file is the literal message text, not just the routing decision.

## Patterns

- **Work gates (Pending / Changes Required / Stale)**: `Due next: Stage.Gate → skill` followed by the capitalized reason. Identical shape across all three gates for a given stage.
- **Approval Required**: `→ human — pdlc post approve` (or `pdlc post complete` at the Verification completion boundary), plus a reauthor-in-place note for the stages where it applies (Product, UI, Tasks, Technical Plan).
- **Approved, stray CI Pending on a non-CI-gated stage, and Verification's stray Review Required (all heal the same lightweight way)**: a short reason line, then `Call \`pdlc next {ITEM_ID}\` to continue this work item.`
- **Decision Required (Product, UI, Tasks, Technical Plan, Verification)**: `Due next: Stage.DecisionRequired → This work item is pending user decision.` plus an `### Evidence` section inlining the newest PDLC-DECISION comment, or the "unable to parse" fallback prose when none is found — same evidence-lookup shape as Changes Required/Stale.
- **Implementation/Testing/Verification CI Pending (genuinely CI-gated, not healed)**: `→ pdlc post ci — record...` plus the read-only resolve-ci.md orientation line.
- **Review Required (Implementation, Testing only)**: `→ pdlc-review`. Verification has no persisted review policy, so its Review Required is a heal instead (see above).
- **Structurally invalid with no heal target (Complete only, beyond Approved)**: `→ blocked — <validate_state error>`.
- **Complete**: `Approved` → `none — record is Complete`; every other gate → `blocked — invalid terminal workflow state...`.

Note: the reason line is just `reason.capitalize()` applied to a lowercase source string, so proper nouns and acronyms inside longer reasons render lowercase mid-sentence (e.g. `Ui or task artifact is due.`, `the registered pr stack's ci outcome`). Pre-existing cosmetic behavior, not introduced by the due-next changes.

## Product

### Product / Pending
```
# Due Next

Due next: Product.Pending → This work item is pending user input.
Invoke {Stage.Product.skill} skill interactively.
Product artifact is due; user must invoke pdlc-write interactively,
and it is not possible to continue autonomously.
```

### Product / Review Required
```
# Due Next

Due next: Product.ReviewRequired → This work item is pending review.
Invoke {Stage.Product.skill} skill and continue its review procedure.
Verify that the work item has been published using `pdlc inspect {ITEM_ID}` and pass
its content to the review.
```

### Product / Changes Required
```
# Due Next

Due next: Product.ChangesRequired → This work item needs changes.
User has requested changes. Inspect the evidence section below. If the required changes are clear,
invoke {Stage.Product.skill} and continue to write the product content. If not, ask the user
what changes are needed. Provide context to the user about this work item, since they might
not understand what we are working on.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-REVIEW or PDLC-DECISION comment's verbatim text, marker and metadata header stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Product.ChangesRequired → This work item needs changes.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### Product / Decision Required
```
# Due Next

Due next: Product.DecisionRequired → This work item is pending user decision.
Inspect the evidence section below, inform the user of the decision required, and record their
choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about
arguments to pass. Call `pdlc guide decisions` for information about how to handle user
decision recording.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-DECISION comment's verbatim text, marker stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Product.DecisionRequired → This work item is pending user decision.
PDLC was unable to parse and identify any evidence for the required decision.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### Product / CI Pending
```
# Due Next

Due next: Product.CIPending → We do not stop for CI at this stage.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### Product / Approval Required
```
# Due Next

Due next: Product.ApprovalRequired → This work item is pending user approval.
Explicit user approval is required. You are not able to continue autonomously.
Ask the user to approve, or if the approval has been provided call `pdlc post approve`.
Use `pdlc post approve --help` for more information about arguments to pass.
```

### Product / Approved
```
# Due Next

Due next: Product.Approved → This work item has been approved to continue.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### Product / Stale
```
# Due Next

Due next: Product.Stale → This work item has been invalidated.
User has invalidated the content generated by the work item. Treat this as rewriting Product.
Invoke {Stage.Product.skill} skill and continue its reauthoring procedure. Inspect the evidence
below to determine the required changes. If they are not clear or if PDLC was unable to provide
them, stop and ask the user.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-INVALIDATED comment's verbatim text}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Product.Stale → This work item has been invalidated.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

## UI

### UI / Pending
```
# Due Next

Due next: UI.Pending → This work item is due for the UI stage.
Invoke {Stage.UI.skill} skill and continue with instructions specified there.
```

### UI / Review Required
```
# Due Next

Due next: UI.ReviewRequired → This work item is pending review.
Invoke {Stage.UI.skill} skill and continue its review procedure.
Verify that the work item has been published using `pdlc inspect {ITEM_ID}` and pass
its content to the review.
```

### UI / Changes Required
```
# Due Next

Due next: UI.ChangesRequired → This work item needs changes.
User has requested changes. Inspect the evidence section below. If the required changes are clear,
invoke {Stage.UI.skill} and continue to write the UI content. If not, ask the user
what changes are needed. Provide context to the user about this work item, since they might
not understand what we are working on.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-REVIEW or PDLC-DECISION comment's verbatim text, marker and metadata header stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: UI.ChangesRequired → This work item needs changes.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### UI / Decision Required
```
# Due Next

Due next: UI.DecisionRequired → This work item is pending user decision.
Inspect the evidence section below, inform the user of the decision required, and record their
choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about
arguments to pass. Call `pdlc guide decisions` for information about how to handle user
decision recording.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-DECISION comment's verbatim text, marker stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: UI.DecisionRequired → This work item is pending user decision.
PDLC was unable to parse and identify any evidence for the required decision.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### UI / CI Pending
```
# Due Next

Due next: UI.CIPending → We do not stop for CI at this stage.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### UI / Approval Required
```
# Due Next

Due next: UI.ApprovalRequired → This work item is pending user approval.
Explicit user approval is required. You are not able to continue autonomously.
Ask the user to approve, or if the approval has been provided call `pdlc post approve`.
Use `pdlc post approve --help` for more information about arguments to pass.
```

### UI / Approved
```
# Due Next

Due next: UI.Approved → This work item has been approved to continue.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### UI / Stale
```
# Due Next

Due next: UI.Stale → This work item has been invalidated.
User has invalidated the content generated by the work item. Treat this as rewriting UI.
Invoke {Stage.UI.skill} skill and continue its reauthoring procedure. Inspect the evidence
below to determine the required changes. If they are not clear or if PDLC was unable to provide
them, stop and ask the user.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-INVALIDATED comment's verbatim text}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: UI.Stale → This work item has been invalidated.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

## Tasks

### Tasks / Pending
```
# Due Next

Due next: Tasks.Pending → This work item is due for the Tasks stage.
Invoke {Stage.Tasks.skill} skill autonomously.
UI or task artifact is due; the driver may invoke {Stage.Tasks.skill} directly,
and it is possible to continue autonomously.
```

### Tasks / Review Required
```
# Due Next

Due next: Tasks.ReviewRequired → This work item is pending review.
Invoke {Stage.Tasks.skill} skill and continue its review procedure.
Verify that the work item has been published using `pdlc inspect {ITEM_ID}` and pass
its content to the review.
```

### Tasks / Changes Required
```
# Due Next

Due next: Tasks.ChangesRequired → This work item needs changes.
User has requested changes. Inspect the evidence section below. If the required changes are clear,
invoke {Stage.Tasks.skill} and continue to write the delivery tasks. If not, ask the user
what changes are needed. Provide context to the user about this work item, since they might
not understand what we are working on.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-REVIEW or PDLC-DECISION comment's verbatim text, marker and metadata header stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Tasks.ChangesRequired → This work item needs changes.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### Tasks / Decision Required
```
# Due Next

Due next: Tasks.DecisionRequired → This work item is pending user decision.
Inspect the evidence section below, inform the user of the decision required, and record their
choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about
arguments to pass. Call `pdlc guide decisions` for information about how to handle user
decision recording.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-DECISION comment's verbatim text, marker stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Tasks.DecisionRequired → This work item is pending user decision.
PDLC was unable to parse and identify any evidence for the required decision.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### Tasks / CI Pending
```
# Due Next

Due next: Tasks.CIPending → We do not stop for CI at this stage.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### Tasks / Approval Required
```
# Due Next

Due next: Tasks.ApprovalRequired → This work item is pending user approval.
Explicit user approval is required. You are not able to continue autonomously.
Ask the user to approve, or if the approval has been provided call `pdlc post approve`.
Use `pdlc post approve --help` for more information about arguments to pass.
```

### Tasks / Approved
```
# Due Next

Due next: Tasks.Approved → This work item has been approved to continue.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### Tasks / Stale
```
# Due Next

Due next: Tasks.Stale → This work item has been invalidated.
User has invalidated the content generated by the work item. Treat this as rewriting Tasks.
Invoke {Stage.Tasks.skill} skill and continue its reauthoring procedure. Inspect the evidence
below to determine the required changes. If they are not clear or if PDLC was unable to provide
them, stop and ask the user.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-INVALIDATED comment's verbatim text}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Tasks.Stale → This work item has been invalidated.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

## Technical Plan

Pending, Changes Required, and Stale each end with a `### Next Pending Task` section: a
task-level pointer naming whichever delivery task still needs a Technical Plan. The other
gates are record-level states reached only once every task's plan is written, so they omit
this section — printing it there would almost always read "no delivery tasks pending," which
is not informative. The section's body resolves to one of two literal lines:
- task pending: `The next task pending a Technical Plan is {TASK_ID}. Call \`pdlc inspect task {TASK_ID}\` for its current content, and \`pdlc inspect task timeline {TASK_ID}\` for its evidence history.`
- none pending: `No delivery tasks are currently pending a Technical Plan.`

### Technical Plan / Pending
```
# Due Next

Due next: TechnicalPlan.Pending → This work item is due for the Technical Plan stage.
Invoke {Stage.TechnicalPlan.skill} skill and continue with instructions specified there.

### Next Pending Task

{NEXT_PLAN_TASK}
```

### Technical Plan / Review Required
```
# Due Next

Due next: TechnicalPlan.ReviewRequired → This work item is pending review.
Invoke {Stage.TechnicalPlan.skill} skill and continue its review procedure.
Verify that the technical plan for all tasks in the work item have been published using
`pdlc inspect task {TASK_IDs}` and pass that content to the review.
```

### Technical Plan / Changes Required
```
# Due Next

Due next: TechnicalPlan.ChangesRequired → This work item needs changes.
User has requested changes. Inspect the evidence section below. If the required changes are clear,
invoke {Stage.TechnicalPlan.skill} and continue to write the technical plan. If not, ask the user
what changes are needed. Provide context to the user about this work item, since they might
not understand what we are working on.

### Next Pending Task

{NEXT_PLAN_TASK}

### Evidence

This evidence was posted at {when}.
{the newest PDLC-REVIEW or PDLC-DECISION comment's verbatim text, marker and metadata header stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: TechnicalPlan.ChangesRequired → This work item needs changes.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.

### Next Pending Task

{NEXT_PLAN_TASK}
```

### Technical Plan / Decision Required
```
# Due Next

Due next: TechnicalPlan.DecisionRequired → This work item is pending user decision.
Inspect the evidence section below, inform the user of the decision required, and record their
choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about
arguments to pass. Call `pdlc guide decisions` for information about how to handle user
decision recording.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-DECISION comment's verbatim text, marker stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: TechnicalPlan.DecisionRequired → This work item is pending user decision.
PDLC was unable to parse and identify any evidence for the required decision.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### Technical Plan / CI Pending
```
# Due Next

Due next: TechnicalPlan.CIPending → We do not stop for CI at this stage.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### Technical Plan / Approval Required
```
# Due Next

Due next: TechnicalPlan.ApprovalRequired → This work item is pending user approval.
Explicit user approval is required. You are not able to continue autonomously.
Ask the user to approve, or if the approval has been provided call `pdlc post approve`.
Use `pdlc post approve --help` for more information about arguments to pass.
```

### Technical Plan / Approved
```
# Due Next

Due next: TechnicalPlan.Approved → This work item has been approved to continue.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### Technical Plan / Stale
```
# Due Next

Due next: TechnicalPlan.Stale → This work item has been invalidated.
User has invalidated the content generated by the work item. Treat this as rewriting the technical plan.
Invoke {Stage.TechnicalPlan.skill} skill and continue its reauthoring procedure. Inspect the evidence
below to determine the required changes. If they are not clear or if PDLC was unable to provide
them, stop and ask the user.

### Next Pending Task

{NEXT_PLAN_TASK}

### Evidence

This evidence was posted at {when}.
{the newest PDLC-INVALIDATED comment's verbatim text}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: TechnicalPlan.Stale → This work item has been invalidated.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.

### Next Pending Task

{NEXT_PLAN_TASK}
```

## Implementation

Pending, Changes Required, and Stale each end with a `### Next Pending Task` section: a
task-level pointer naming whichever delivery task is next eligible for implementation. The
other gates are record-level states reached only once every eligible task has been
implemented, so they omit this section. The section's body resolves to one of two literal
lines:
- task pending: `The next task pending implementation is {TASK_ID}. Call \`pdlc inspect task {TASK_ID}\` for its current content, and \`pdlc inspect task timeline {TASK_ID}\` for its evidence history.`
- none pending: `No delivery tasks are currently pending implementation.`

### Implementation / Pending
```
# Due Next

Due next: Implementation.Pending → This work item is due for the Implementation stage.
Invoke {Stage.Implementation.skill} skill and continue with instructions specified there.

### Next Pending Task

{NEXT_IMPLEMENTATION_TASK}
```

### Implementation / Review Required
```
# Due Next

Due next: Implementation.ReviewRequired → This work item is pending review.
Invoke {REVIEW_SKILL} skill with this work item's number. Pass the correct scope.
Default scope is every task delivered in the current publication pass;
if the user named a specific task or asked for a full audit, carry that scope into the
dispatch instead of the default.
```

`{REVIEW_SKILL}` resolves from `due["action"]` (`Action.REVIEW.value`, currently `"pdlc-review"`) —
the same source `_due_next_section` already computes for this gate, so the reviewing skill's
name is never a literal string in the code, only in this doc's illustrative rendering.

Unlike Product, UI, Tasks, and Technical Plan, Implementation and Testing are reviewed by
that dispatcher rather than by re-entering their own owning skill — see `pdlc-review/SKILL.md`:
those four stages are reviewed locally before publication by their owning skill, so reaching
`Review Required` there means something published without going through that step, whereas
Implementation and Testing reach `Review Required` as their normal, intended path. That's why
this text names `{REVIEW_SKILL}` rather than `{Stage.Implementation.skill}` — the reviewing
skill isn't the owning skill here — and tells the agent what to gather instead of a single
`pdlc inspect` call, since Implementation review evidence spans PRs, diffs, checks, and task
Results rather than one artifact body.

### Implementation / Changes Required
```
# Due Next

Due next: Implementation.ChangesRequired → This work item needs changes.
User has requested changes. Inspect the evidence section below. If the required changes are clear,
invoke {Stage.Implementation.skill} and continue implementing the next eligible delivery task. If not, ask
the user what changes are needed. Provide context to the user about this work item, since they might
not understand what we are working on.

### Next Pending Task

{NEXT_IMPLEMENTATION_TASK}

### Evidence

This evidence was posted at {when}.
{the newest PDLC-REVIEW or PDLC-DECISION comment's verbatim text, marker and metadata header stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Implementation.ChangesRequired → This work item needs changes.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.

### Next Pending Task

{NEXT_IMPLEMENTATION_TASK}
```

### Implementation / Decision Required
```
# Due Next

Due next: Implementation.DecisionRequired → This work item is pending user decision.
Inspect the evidence section below, inform the user of the decision required, and record their
choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about
arguments to pass. Call `pdlc guide decisions` for information about how to handle user
decision recording.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-DECISION comment's verbatim text, marker stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Implementation.DecisionRequired → This work item is pending user decision.
PDLC was unable to parse and identify any evidence for the required decision.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### Implementation / CI Pending
```
# Due Next

Due next: Implementation.CIPending → This work item is pending CI build.
Call `pdlc post ci {ITEM_ID}` to check for the CI gates, do not use internal gh cli
directly as it doesn't configure the pdlc state after CI failure. Act on the instructions
provided by that command.
```

### Implementation / Approval Required
```
# Due Next

Due next: Implementation.ApprovalRequired → This work item is pending user approval.
Explicit user approval is required. You are not able to continue autonomously.
Ask the user to approve, or if the approval has been provided call `pdlc post approve`.
Use `pdlc post approve --help` for more information about arguments to pass.
```

### Implementation / Approved
```
# Due Next

Due next: Implementation.Approved → This work item has been approved to continue.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### Implementation / Stale
```
# Due Next

Due next: Implementation.Stale → This work item has been invalidated.
User has invalidated one or more delivery tasks' implementation. `pdlc post invalidate` reopens
those tasks specifically (`--task`), the same task-scoped invalidation Technical Plan uses.
Invoke {Stage.Implementation.skill} skill and continue implementing the reopened task(s). Inspect
the evidence below to determine the required changes. If they are not clear or if PDLC was unable
to provide them, stop and ask the user.

### Next Pending Task

{NEXT_IMPLEMENTATION_TASK}

### Evidence

This evidence was posted at {when}.
{the newest PDLC-INVALIDATED comment's verbatim text}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Implementation.Stale → This work item has been invalidated.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.

### Next Pending Task

{NEXT_IMPLEMENTATION_TASK}
```

## Testing

Testing is not task-scoped the way Technical Plan and Implementation are: there is no single
"next eligible task" to point at, and `pdlc post invalidate` cannot target one task with
`--task` here (`TASK_SCOPED_STAGES` in `internal/invalidation.py` names only Technical Plan
and Implementation). So Pending, Changes Required, and Stale end with a `### Testable Scope`
section instead of a `### Next Pending Task` one — pointing at the real, always-runnable
`pdlc inspect test {ITEM_ID}`, which reports every delivery task closed with its
implementation recorded, its linked PRs, and the files those PRs touched.

### Testing / Pending
```
# Due Next

Due next: Testing.Pending → This work item is due for the Testing stage.
Invoke {Stage.Testing.skill} skill and continue with instructions specified there.

### Testable Scope

Call `pdlc inspect test {ITEM_ID}` for the current testable scope: every delivery task closed
with its implementation recorded, its linked PRs, and the files those PRs touched.
```

### Testing / Review Required
```
# Due Next

Due next: Testing.ReviewRequired → This work item is pending review.
Invoke {REVIEW_SKILL} skill with this work item's number.
```

Same `{REVIEW_SKILL}` source as Implementation's Review Required — see that section's note.
Genuine difference: an Implementation review takes a depth (`pass`/`task`/`full`); a Testing
review always covers the whole artifact, so this text has no scope-carrying paragraph
(`pdlc-review/SKILL.md`: "Only an Implementation review takes a depth").

### Testing / Changes Required
```
# Due Next

Due next: Testing.ChangesRequired → This work item needs changes.
Inspect the evidence section below. If the required changes are clear,
invoke {Stage.Testing.skill} and continue writing acceptance coverage. If not, ask
the user what changes are needed. Provide context to the user about this work item, since they might
not understand what we are working on.

### Testable Scope

Call `pdlc inspect test {ITEM_ID}` for the current testable scope: every delivery task closed
with its implementation recorded, its linked PRs, and the files those PRs touched.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-REVIEW or PDLC-DECISION comment's verbatim text, marker and metadata header stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Testing.ChangesRequired → This work item needs changes.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.

### Testable Scope

Call `pdlc inspect test {ITEM_ID}` for the current testable scope: every delivery task closed
with its implementation recorded, its linked PRs, and the files those PRs touched.
```

### Testing / Decision Required
```
# Due Next

Due next: Testing.DecisionRequired → This work item is pending user decision.
Inspect the evidence section below, inform the user of the decision required, and record their
choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about
arguments to pass. Call `pdlc guide decisions` for information about how to handle user
decision recording.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-DECISION comment's verbatim text, marker stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Testing.DecisionRequired → This work item is pending user decision.
PDLC was unable to parse and identify any evidence for the required decision.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### Testing / CI Pending
```
# Due Next

Due next: Testing.CIPending → This work item is pending CI build.
Call `pdlc post ci {ITEM_ID}` to check for the CI gates, do not use internal gh cli
directly as it doesn't configure the pdlc state after CI failure. Act on the instructions
provided by that command.
```

Same shape as Implementation's CI Pending: Testing is CI-gated too (`stage-ownership.md`),
genuinely checked via `pdlc post ci`, not healed.

### Testing / Approval Required
```
# Due Next

Due next: Testing.ApprovalRequired → This work item is pending user approval.
Explicit user approval is required. You are not able to continue autonomously.
Ask the user to approve, or if the approval has been provided call `pdlc post approve`.
Use `pdlc post approve --help` for more information about arguments to pass.
```

### Testing / Approved
```
# Due Next

Due next: Testing.Approved → This work item has been approved to continue.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### Testing / Stale
```
# Due Next

Due next: Testing.Stale → This work item has been invalidated.
User has invalidated this work item's testing artifact. Invoke {Stage.Testing.skill} skill
and continue writing acceptance coverage for the required changes.
Inspect the evidence below to determine what changed. If they are not clear or if PDLC was
unable to provide them, stop and ask the user.

### Testable Scope

Call `pdlc inspect test {ITEM_ID}` for the current testable scope: every delivery task closed
with its implementation recorded, its linked PRs, and the files those PRs touched.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-INVALIDATED comment's verbatim text}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Testing.Stale → This work item has been invalidated.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.

### Testable Scope

Call `pdlc inspect test {ITEM_ID}` for the current testable scope: every delivery task closed
with its implementation recorded, its linked PRs, and the files those PRs touched.
```

## Verification

Verification is not task-scoped — there is no delivery-task pointer or testable-scope block
the way Technical Plan/Implementation/Testing have, so Pending, Changes Required, and Stale
carry no extra section beyond the standard `### Evidence` lookup. Two gates differ genuinely
from the shape used by every curated stage before it:
- **Review Required** has no persisted review policy at this stage (`stage-ownership.md`), so
  instead of dispatching a review it heals straight to Approval Required via `pdlc next`, the
  same lightweight shape as a stray CI Pending on a non-CI-gated stage.
- **CI Pending** is genuinely CI-gated, same as Implementation/Testing — checked via
  `pdlc post ci`, not healed away.
- **Approval Required** is the completion boundary: it calls out `pdlc post complete`, not
  `pdlc post approve`, since approving here moves the record to Complete rather than to
  another stage.

### Verification / Pending
```
# Due Next

Due next: Verification.Pending → This work item is due for the Verification stage.
Invoke {Stage.Verification.skill} skill and continue with instructions specified there.
```

### Verification / Review Required
```
# Due Next

Due next: Verification.ReviewRequired → This stage does not require any additional reviewing.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### Verification / Changes Required
```
# Due Next

Due next: Verification.ChangesRequired → This work item needs changes.
Inspect the evidence section below. If the required changes are clear,
invoke {Stage.Verification.skill} and continue re-verifying the required scope. If not, ask
the user what changes are needed. Provide context to the user about this work item, since they might
not understand what we are working on.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-REVIEW or PDLC-DECISION comment's verbatim text, marker and metadata header stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Verification.ChangesRequired → This work item needs changes.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### Verification / Decision Required
```
# Due Next

Due next: Verification.DecisionRequired → This work item is pending user decision.
Inspect the evidence section below, inform the user of the decision required, and record their
choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about
arguments to pass. Call `pdlc guide decisions` for information about how to handle user
decision recording.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-DECISION comment's verbatim text, marker stripped}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Verification.DecisionRequired → This work item is pending user decision.
PDLC was unable to parse and identify any evidence for the required decision.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

### Verification / CI Pending
```
# Due Next

Due next: Verification.CIPending → This work item is pending CI build.
Call `pdlc post ci {ITEM_ID}` to check for the CI gates, do not use internal gh cli
directly as it doesn't configure the pdlc state after CI failure. Act on the instructions
provided by that command.
```

### Verification / Approval Required
```
# Due Next

Due next: Verification.ApprovalRequired → This work item is pending user approval.
Explicit user approval is required. You are not able to continue autonomously.
Ask the user to approve, or if the approval has been provided call `pdlc post complete`.
Use `pdlc post complete --help` for more information about arguments to pass.
```

### Verification / Approved
```
# Due Next

Due next: Verification.Approved → This work item has been approved to continue.
Call `pdlc next {ITEM_ID}` to continue this work item.
```

### Verification / Stale
```
# Due Next

Due next: Verification.Stale → This work item has been invalidated.
User has invalidated this work item's verification. Invoke {Stage.Verification.skill} skill
and continue re-verifying the required scope. Inspect the evidence below to determine what
changed. If they are not clear or if PDLC was unable to provide them, stop and ask the user.

### Evidence

This evidence was posted at {when}.
{the newest PDLC-INVALIDATED comment's verbatim text}

Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item.
```

or, when no matching evidence comment is found — no `### Evidence` heading, folded directly into the Due Next body:
```
# Due Next

Due next: Verification.Stale → This work item has been invalidated.
PDLC was unable to parse and identify any evidence for the required changes.
Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear
in the conversation so far. Read the user's comments on the work item
(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request
the user's confirmation before continuing. Do not assume anything — this work
item is no longer able to continue autonomously.
```

## Complete

### Complete / Pending
```
# Due Next

Due next: Complete.Pending → blocked — invalid terminal workflow state: Complete / Pending / Completed
Invalid terminal workflow state: complete / pending / completed.
```

### Complete / Review Required
```
# Due Next

Due next: Complete.ReviewRequired → blocked — invalid terminal workflow state: Complete / Review Required / Completed
Invalid terminal workflow state: complete / review required / completed.
```

### Complete / Changes Required
```
# Due Next

Due next: Complete.ChangesRequired → blocked — invalid terminal workflow state: Complete / Changes Required / Completed
Invalid terminal workflow state: complete / changes required / completed.
```

### Complete / Decision Required
```
# Due Next

Due next: Complete.DecisionRequired → blocked — invalid terminal workflow state: Complete / Decision Required / Completed
Invalid terminal workflow state: complete / decision required / completed.
```

### Complete / CI Pending
```
# Due Next

Due next: Complete.CIPending → blocked — invalid terminal workflow state: Complete / CI Pending / Completed
Invalid terminal workflow state: complete / ci pending / completed.
```

### Complete / Approval Required
```
# Due Next

Due next: Complete.ApprovalRequired → blocked — invalid terminal workflow state: Complete / Approval Required / Completed
Invalid terminal workflow state: complete / approval required / completed.
```

### Complete / Approved
```
# Due Next

Due next: Complete.Approved → none — record is Complete
Complete.
```

### Complete / Stale
```
# Due Next

Due next: Complete.Stale → blocked — invalid terminal workflow state: Complete / Stale / Completed
Invalid terminal workflow state: complete / stale / completed.
```
