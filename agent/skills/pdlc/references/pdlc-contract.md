# PDLC contract

The PDLC work item store is the system of record; local files are temporary
inputs only. The `pdlc` CLI commands are the only interface to it — never assume a
particular backing store.

## Record ownership

- The parent work item owns the canonical product specification, decisions,
  open questions, phase artifacts, and durable evidence.
- The work item's own state owns the current `Status`, current-gate `Gate
  State`, `Lifecycle`, `Slug`, and queue metadata.
- Delivery tasks own their own scope, dependencies, acceptance criteria,
  plans, implementation links, and task evidence. A delivery task is never a
  work item in its own right.
- Pull requests own code and test changes. They must link the relevant task and
  parent work item.
- Evidence comments are append-only and explain transitions. Never
  use a comment as a substitute for work item state.

## Local attachments

Attachments are local agent inputs, not PDLC record data. `pdlc post` commands may save
them under `.pdlc/<work-item-number>/attachments/`; inspectors read that local
directory and render the attachment description and path. Attachment metadata
and file contents are never written to the work item, Project, issue, or
evidence comments.

## Referring to requirements

`FR-*`, `C-*`, and `UJ-*` identifiers exist for machine coverage checks, not for communicating with a person.
Any human-read output — driver reports, questions, review summaries, evidence-comment bodies — that cites one quotes or paraphrases the requirement alongside the tag, so the reader never has to look the identifier up.

## Identity

A resolved parent record carries a normalized `workType`. Native GitHub Issue Type `Feature` resolves to `feature`; legacy records with no type use the Feature pipeline for compatibility. Unknown types and known unavailable pipelines are blocked. Pipeline selection happens once when the record is resolved; commands use that selected policy for routing, transitions, invalidation, churn, and completion.

A work item registered with PDLC is a parent record; one without is not. `Slug`
is a stable machine identifier set once by `pdlc post write` at creation and
never rewritten afterward. The title remains human-readable and free to reword.
The controller matches stable work item numbers and IDs, never titles
or in-body markers.

## Stages and gates

The enabled Feature pipeline stores its active stage in the work item's `Status`:

`Product → UI → Tasks → Technical Plan → Implementation → Testing → Verification → Complete`

`Gate State` describes the active stage:

`Pending | Review Required | Changes Required | Decision Required | CI Pending | Approval Required | Approved | Stale`

`CI Pending` is set on `Implementation` when a clean stage review lands but the
task PR stack's checks have not finished — the reviewer judged the code while CI
was still in flight. It is not a human gate: `pdlc post ci` reconciles it against
the live check state across every PR in the stack — all green, or no checks
configured, advances to `Approval Required`; any red posts a
`PDLC-IMPLEMENTATION` note and drops to `Changes Required`. The autonomous loop
backs off while checks run, then resolves it with no human involvement.

`Decision Required` is set by a post-publication reviewer (Implementation,
Testing), or by the Verification audit itself (`pdlc post verify
--recommendation "Decision Required" --decision`), when a finding turns on a
product, architecture, UX, safety, or scope call the owning skill cannot make.
It halts the autonomous loop with no reconciliation passes, and its evidence —
a `## Decision Required` block stating the question, options, recommendation,
and what it blocks — is posted through the backend's blocker channel under
`PDLC-DECISION`.

Only the driver clears it, through `references/decision-resolver-workflow.md`:
`pdlc post decision` takes a manifest of per-decision outcomes — each either
answered or deferred into its own `Product / Pending` work item — records them
all under one `PDLC-RESOLUTION` comment, and moves the gate to `Changes
Required`, which routes back to the stage owner (`pdlc-implement`, `pdlc-test`,
or `pdlc-verify`). A decision that invalidates approved upstream intent goes
through `pdlc post invalidate` against the owning stage instead.

The normal phase loop is:

`Pending/Changes Required/Stale → phase work → Review Required → independent review → Approval Required → explicit human approval → next stage Pending`

Only the local controller may mutate work item fields. Agents request transitions
through it. `pdlc post approve`, `pdlc post skip`, and `pdlc post complete` carry no
identity check — every agent acts under the driver's own credentials, so an
identity match proves nothing. The boundary is procedural: only the orchestrator
calls these commands, and only in direct response to the human's own words in this
turn, never inferred from conversation or a specialist's recommendation. A
human approval is recorded as a work item comment and atomically advances the
record to the next stage at `Pending`. Verification is the exception: its
approval is consumed by the completion transition.

The work item has one active stage, not a hidden map of all historical gate
states. Historical phase status is preserved in evidence comments and artifact
markers. When an upstream artifact changes, move the work item back to that
stage, set `Gate State = Stale`, set `Lifecycle = Planning`, and
record which downstream evidence is invalidated.

## Transition policy

- Product authoring is never autonomous. `pdlc-write` interviews the driver,
  has the draft reviewed locally, and creates or updates the record only once
  that review is clean — landing it at `Product / Approval Required`.
- Product work routes to `human-input`; the autonomous loop stops and asks the driver to invoke `pdlc-write` interactively.
- The pre-publication stages (`Product`, `UI`, `Tasks`, `Technical Plan`) reach
  `Approval Required` directly. A driver request to change one of them before it
  is approved is handled by that stage's own land script
  (`pdlc post write` / `pdlc post tasks` / `pdlc post plan`): it resets
  the gate to `Stale` itself and re-lands the reviewed artifact in one call. No
  `PDLC-INVALIDATED` comment — the artifact never settled at `Approved`, the
  re-land's own stage evidence records the change, and nothing feeds the
  rework/churn total. No separate `pdlc post invalidate` step.
- Every later stage transition requires the current stage to be `Approval Required` and an explicit human approval. The one exception: when a record has already entered its named rework loop between one and three times, counted from Verification `PDLC-REVIEW` comments with `verdict: Changes Required`, a non-null `bounce`, and the matching `loop`, the script that would set the `Implementation` or `Testing` `Approval Required` gate advances straight past it instead. It posts `PDLC-AUTOAPPROVED` and lands the next stage's `Pending`. Past the selected pipeline's rework cap (three for Feature), the gate stops for the driver again; `Verification` approval is never auto-cleared. A `Verification` `Changes Required` run bounces `Implementation` or `Testing` to `Stale` on its own when invoked with `pdlc post verify --bounce STAGE`.
- Agents may set `Review Required`, `Changes Required`, `Decision Required`, `CI Pending`, and `Approval Required`.
- Agents may not set `Approved` or `Complete`. Only the churn auto-approval in
  the CI gate / `pdlc post review` advances a stage without a recorded
  human approval, within the bounds above.
- `Complete` requires clean Verification evidence, all delivery tasks closed,
  the record's registered PRs merged, and passing required checks.
- A record's pull requests are read from the explicit registry on the work item
  and its tasks (`pdlc post implement-task` / `attach-pr` / `implement` / `test`
  record them), never inferred from a `Closes #N` keyword or a branch name.
- `Complete` is locked. New scope creates a new parent work item.
- A malformed state, unknown work type, or unavailable pipeline is `blocked`; report the reason and never guess.

## Phase ownership

- Product: problem, goals, requirements, constraints, non-goals, success,
  assumptions, decisions, and open questions.
- UI: UI specification, accessibility, states, and user journeys.
- Tasks: stable `WORK-NNN-TASK-NNN` delivery tasks with requirements,
  dependencies, acceptance criteria, and HITL/AFK classification.
- Technical Plan: source ownership, architecture, sequencing, risks, and
  validation plan.
- Implementation: production changes plus each task's unit coverage, one
  stacked PR per delivery task, and result evidence. `pdlc-implement` lands one
  task per invocation; the parent remains at `Implementation / Pending` while
  any delivery task is open, and only after all task evidence is settled does it
  enter phase review. Each task PR is opened as a draft; `pdlc post implement`
  takes the whole open stack out of draft as the record enters phase review.
- Testing: whole-feature requirement traceability, acceptance coverage, and CI
  evidence across the task PR stack.
- Verification: claims, runtime behavior, UX journeys, review findings, and
  completion recommendation.

## Artifact structure

The parent work item body uses stable, named sections for Product, UI, Decisions, Open Questions, and Verification.
Pull requests are attached to a record — and, in the stacked flow, to each delivery task — through the backend, which owns how the link is stored; a body carries human-authored content only.
A stage owner may prepare a replacement only for its owned section and must preserve approved upstream sections.
Controller scripts re-read the live record before publishing it.
Completion is not a stage owner of any section: `pdlc post complete` records what shipped in its evidence comment and makes exactly one section edit — blanking the settled Open Questions section to a pointer.

## Evidence markers

Every evidence comment starts with one of these markers so the controller and
humans can find durable evidence without parsing prose. **No agent writes one.**
The `pdlc post *` commands stamp the marker from the calling command's own
knowledge of the stage, refuse an evidence file that already carries one, and
refuse an unknown or missing marker with the valid list. Evidence files hold the
comment body only:

- `PDLC-PRODUCT`
- `PDLC-UI`
- `PDLC-TASKS`
- `PDLC-PLAN`
- `PDLC-IMPLEMENTATION`
- `PDLC-TESTING`
- `PDLC-REVIEW` — a structured independent-review verdict with a script-owned, `---`-delimited metadata block containing `stage`, `verdict`, `bounce`, and `loop`, followed by `## Findings`; Verification reports use the same marker and retain their detailed report sections.
- `PDLC-COMPLETE`
- `PDLC-APPROVED` — a driver approved a stage (`pdlc post approve`)
- `PDLC-AUTOAPPROVED` — the `Implementation`/`Testing` approval gate was cleared with no human step on a churning record (the CI gate, `pdlc post review`)
- `PDLC-INVALIDATED` — a driver returned a settled stage to `Stale` with `pdlc post invalidate`; the comment opens with a script-owned `Invalidated stage: <stage>` line. It does not count as a Verification rework loop. (A pre-publication stage re-authored in place from `Approval Required` posts no such comment — it is a bare gate reset.) Invalidating to `Technical Plan` or `Implementation` also reopens delivery tasks Implementation had already closed — every closed task by default, or only the tasks named by repeated `--task TASK_NUMBER` — so each is back in scope for planning/implementation; every reopened task gets its own `PDLC-INVALIDATED` comment on the task thread. `--task` is rejected for any other target stage, since they carry no per-task evidence to reopen.
- `PDLC-SKIPPED` — a stage declared skipped, or auto-advanced past (`pdlc post skip`, `pdlc next`)
- `PDLC-DECISION`
- `PDLC-RESOLUTION`

Each evidence comment should include the work item/PR links, actor, timestamp,
scope, result, and unresolved risks. Specialists prepare the body; the commands
stamp, publish, and record the validated stage transition.

One exception: a delivery task's per-task Technical Plan and implementation
note are each a plain comment on the delivery task whose first non-empty line is
`## Technical Plan` or `## Implementation` — no marker. `pdlc post plan` and
`pdlc post implement-task` post them (the latter prepends the
`## Implementation` heading when the supplied summary omits it), and
`pdlc-inspect` derives the
`hasPlan` / `hasImplementation` flags (and renders the plan) from those
headings. Unlike other evidence, a task's `## Technical Plan` comment is not
append-only: a re-plan replaces it in place, so a task never carries more than
one. The parent's `Technical Plan` / `PDLC-IMPLEMENTATION` markers still
belong to the respective *stage* publication evidence.

Every script that posts evidence takes the body as a file path, or as
`text:<body>` for a short one-line body passed as a single argument. An unknown
path is an error, never a silent literal; empty evidence is always refused.

## Determinism and idempotency

- Re-running a phase must update the same parent work item sections or stable task
  IDs instead of creating duplicates.
- Re-running record creation, field updates, or comments must not silently select
  a different record.
- Every mutation must address its target by explicit ID and validate the
  response.
- Backend failures, missing fields, rate limits, and ambiguous matches are hard
  failures, not reasons to continue.
