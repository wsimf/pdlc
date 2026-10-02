#!/usr/bin/env python3
"""NAME
    pdlc inspect - read-only: work-item overview, task tree, PRs, and routing decision

USAGE
    pdlc inspect ISSUE_NUMBER
    pdlc inspect ISSUE_NUMBER --full
    pdlc inspect ISSUE_NUMBER --file

FLAGS
    --full    print the complete inspection on stdout instead of a compact index
    --file    print the complete inspection's cache-file path instead of a compact index

DESCRIPTION
    Renders a work item's metadata, task tree, linked pull requests,
    and routing decision for the pdlc skill's Orient mode.

Sections are ordered front matter, `# Work Item` (or `# Requirements` for an
uninitialized work item), `## Attachments`,
`## User Comments`, `# Tasks`, `# Warnings` (only when there is one),
`# Due Next`.

`## Attachments` lists local Work Item attachments with their descriptions and
resolved paths. `## User Comments` carries every comment on the record that has
no `PDLC-*` marker — human or outside-bot discussion — oldest first; one comment
fetch feeds both the full and compact renders.

By default the complete inspection is written to the configured work-item cache
and stdout carries a compact index.

Always includes a `# Tasks` section: every delivery task as its own YAML
front-matter block (number, title, completed, isUI, hasPlan,
hasImplementation, implementationInvalidated, needsPlan) — metadata only, no
body. `hasPlan` is true once a task has a `## Technical Plan` comment;
`needsPlan` tracks that directly (open and no plan comment). `hasImplementation`
is true once a pull request is attached to the task — it survives invalidation,
since invalidation only deletes evidence comments, not the PR itself.
`implementationInvalidated` is true when a PR is attached but the task's
`## Implementation` comment is missing, i.e. reopened for rework since it was
last implemented. A single GraphQL call computes every flag, so this costs
nothing extra; it omits the body text itself, which is usually only needed for
a handful of tasks. Fetch those with
`pdlc inspect task DELIVERY_TASK [DELIVERY_TASK ...]`. Dependency closure
still requires reading a candidate's body and the record's own
comments; this stops short of that judgment. Evidence comments are
deliberately not included — they are read through their own script.

`# Warnings` appears when the Gate State claims more than the record's own
evidence shows, one bullet each: Review Required on Implementation or Testing
with no current publication to review; Approval Required, CI Pending, or a
stray Approved that would advance, where the stage's latest publication is
missing, has a change request open since it, or (Implementation, Testing)
has no passing review — the evidence `pdlc post approve` requires; and CI
Pending on Implementation or Testing with no registered pull request. It
reports and never corrects, and `# Due Next` still routes on the gate.

Also includes a `# Due Next` section: the same `(Status, Gate State) → action`
table pdlc next routes on, applied read-only — it looks ahead through
any consecutive stages declared in `Skipped States` the same way that script's
skip cascade does, but never posts a comment or writes work item state. This is
what tells a caller what's actually due without hand-applying the table in
pdlc/SKILL.md itself.

The default compact output retains the metadata, task tree, and routing needed
for orientation, and points at the full file with the raw work item body.

    ---
    id: PVTI_...                        work item ID, not the work item ID
    content:
      number: 18
      title: "..."
      url: "..."
    Status: Product                     work item fields; any of
    Gate State: Approval Required       the three may be null
    Lifecycle: Planning
    Skipped States: ""                  comma-joined stage names, or empty
    pullRequests:                       registered on the record + its tasks
      - number: 139
        title: "..."
        url: "..."
        state: OPEN | CLOSED | MERGED
        isDraft: false
        branch: "feat/..."             head ref
        mergedAt: "..." | null
        checks: SUCCESS | FAILURE | PENDING | ... | NONE
    ---

    # Work Item

    Full body in <cache-root>/.pdlc/cache/18/pdlc-18-<random>.md
    Read lines 14-48 in <cache-root>/.pdlc/cache/18/pdlc-18-<random>.md for the body.

    ## Attachments

    ## User Comments

    # Tasks

    ---
    number: 45
    title: "WORK-42-TASK-001 [CORE] Add foo"
    completed: false
    isUI: false
    hasPlan: true
    hasImplementation: false
    implementationInvalidated: false
    needsPlan: false
    ---

    # Due Next

    Due next: Implementation.Pending → pdlc-implement
    Next eligible delivery task is due.

or, with one or more stages bypassed via `Skipped States`:

    # Due Next

    Skipped through: UI, Tasks (declared in Skipped States)
    Due next: Technical Plan.Pending → pdlc-plan
    Technical plan is due.

A stage/gate combination no pdlc command ever writes, but with exactly one
sane correction (see `pdlc continue --help`), reports that correction as the
due-next action instead of blocked — a stray `Approved`, a stray `CI Pending`
on a stage that isn't CI-gated, or (Verification only) a stray `Review
Required` on a stage with no persisted review policy. Every Feature-pipeline
stage is fully curated (see `_STAGE_DUE_NEXT`), so these heals always render
through their own gate's curated text instead of this generic
`pdlc continue — self-heals to X` fallback shape — see Product's `Approved`,
or Verification's `Review Required` and `CI Pending`, below.

A stage with no curated Due Next text would fall back to this same generic
form for a Decision Required gate too, carrying explicit instructions since
resolving it needs a human answer the agent cannot infer on its own — but
every Feature-pipeline stage curates Decision Required as well, inlining the
newest PDLC-DECISION comment under `### Evidence`, so this form is currently
unreachable there too. Changes Required and Stale instead summarise, under
`### Open Changes`, every change request the stage has not addressed since it
last published (see `pdlc inspect changes --help`), and point at that command
for their full text. Approval Required lists, under `### Patches Since Last
Approval`, every PDLC-PATCHED comment newer than the record's last approval —
upstream artifacts corrected in place that the driver has not approved past —
each with the requirement ids it added, removed, or reworded, if any.

Product, UI, Tasks, Technical Plan, Implementation, Testing, and Verification
all carry curated, per-gate text (see `_STAGE_DUE_NEXT`); the terminal
`Complete` stage instead always renders one fixed message — "This work item
has been completed." — regardless of its gate, since nothing is due next once
a record is terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


from pdlc.internal.pull_requests import record_pull_requests
from pdlc.internal.attachments import attachments_for_item, attachments_markdown
from pdlc.domain.changes import evidence_warnings, open_change_requests, open_changes_summary
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.patch import patches_since_approval
from pdlc.domain.model import evidence_comment_text, item_issue, latest_marked_comment, timeline_formatted_at
from pdlc.domain.workflow import Lifecycle, State
from pdlc.internal.reporting import older_comments_notice, yaml_front_matter
from pdlc.internal.scratch import scratch_path, write_scratch
from pdlc.internal.workitem import (
    comments_and_tasks,
    due_next,
    is_stage_skipped,
    item_gate,
    item_skipped_states,
    item_status,
    pipeline_for_item,
    record_snapshot,
    user_comments_markdown,
)
from pdlc.domain.workflows.stages import (
    IMPLEMENTATION_STAGE,
    PRODUCT_STAGE,
    TASKS_STAGE,
    TECHNICAL_PLAN_STAGE,
    TESTING_STAGE,
    UI_STAGE,
    VERIFICATION_STAGE,
)
from pdlc.internal.failure import report_failure


# Product, UI, and Tasks are the independently-reviewable stages whose Due
# Next text is written per-gate rather than assembled from the generic
# action/reason shape other stages still use. `{Stage.<name>.skill}` is the
# only substitution — pulled from the stage's own `skill` field so the skill
# name is never hardcoded here — and is resolved via `_STAGE_DUE_NEXT`.
_PRODUCT_DUE_NEXT: dict[str, str] = {
    "Pending": (
        "Due next: Product.Pending → This work item is pending user input.\n"
        "Invoke {Stage.Product.skill} skill interactively.\n"
        "Product artifact is due; user must invoke {Stage.Product.skill} interactively,\n"
        "and it is not possible to continue autonomously."
    ),
    "Review Required": (
        "Due next: Product.ReviewRequired → This work item is pending review.\n"
        "Invoke {Stage.Product.skill} skill and continue its review procedure.\n"
        "Verify that the work item has been published using `pdlc inspect {ITEM_ID}` and pass\n"
        "its content to the review."
    ),
    "Changes Required": (
        "Due next: Product.ChangesRequired → This work item needs changes.\n"
        "User has requested changes. Inspect the open changes below. If the required changes are clear,\n"
        "invoke {Stage.Product.skill} and continue to write the product content. If not, ask the user\n"
        "what changes are needed. Provide context to the user about this work item, since they might\n"
        "not understand what we are working on."
    ),
    "Decision Required": (
        "Due next: Product.DecisionRequired → This work item is pending user decision.\n"
        "Inspect the evidence section below, inform the user of the decision required, and record their\n"
        "choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about\n"
        "arguments to pass. Call `pdlc guide decisions` for information about how to handle user\n"
        "decision recording."
    ),
    "CI Pending": (
        "Due next: Product.CIPending → We do not stop for CI at this stage.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Approval Required": (
        "Due next: Product.ApprovalRequired → This work item is pending user approval.\n"
        "Explicit user approval is required. You are not able to continue autonomously.\n"
        "Ask the user to approve.\n"
        "If user requests changes, follow the re-author procedure specified in the skill, or if approves call `pdlc post approve`.\n"
        "Use `pdlc post approve --help` for more information about arguments to pass."
    ),
    "Approved": (
        "Due next: Product.Approved → This work item has been approved to continue.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Stale": (
        "Due next: Product.Stale → This work item has been invalidated.\n"
        "User has invalidated the content generated by the work item. Treat this as rewriting Product.\n"
        "Invoke {Stage.Product.skill} skill and continue its reauthoring procedure. Inspect the open changes\n"
        "below to determine the required changes. If they are not clear or if PDLC was unable to provide\n"
        "them, stop and ask the user."
    ),
}

_UI_DUE_NEXT: dict[str, str] = {
    "Pending": (
        "Due next: UI.Pending → This work item is due for the UI stage.\n"
        "Invoke {Stage.UI.skill} skill and continue with instructions specified there."
    ),
    "Review Required": (
        "Due next: UI.ReviewRequired → This work item is pending review.\n"
        "Invoke {Stage.UI.skill} skill and continue its review procedure.\n"
        "Verify that the work item has been published using `pdlc inspect {ITEM_ID}` and pass\n"
        "its content to the review."
    ),
    "Changes Required": (
        "Due next: UI.ChangesRequired → This work item needs changes.\n"
        "User has requested changes. Inspect the open changes below. If the required changes are clear,\n"
        "invoke {Stage.UI.skill} and continue to write the UI content. If not, ask the user\n"
        "what changes are needed. Provide context to the user about this work item, since they might\n"
        "not understand what we are working on."
    ),
    "Decision Required": (
        "Due next: UI.DecisionRequired → This work item is pending user decision.\n"
        "Inspect the evidence section below, inform the user of the decision required, and record their\n"
        "choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about\n"
        "arguments to pass. Call `pdlc guide decisions` for information about how to handle user\n"
        "decision recording."
    ),
    "CI Pending": (
        "Due next: UI.CIPending → We do not stop for CI at this stage.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Approval Required": (
        "Due next: UI.ApprovalRequired → This work item is pending user approval.\n"
        "Explicit user approval is required. You are not able to continue autonomously.\n"
        "Ask the user to approve.\n"
        "If user requests changes, follow the re-author procedure specified in the skill, or if approves call `pdlc post approve`.\n"
        "Use `pdlc post approve --help` for more information about arguments to pass."
    ),
    "Approved": (
        "Due next: UI.Approved → This work item has been approved to continue.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Stale": (
        "Due next: UI.Stale → This work item has been invalidated.\n"
        "User has invalidated the content generated by the work item. Treat this as rewriting UI.\n"
        "Invoke {Stage.UI.skill} skill and continue its reauthoring procedure. Inspect the open changes\n"
        "below to determine the required changes. If they are not clear or if PDLC was unable to provide\n"
        "them, stop and ask the user."
    ),
}

_TASKS_DUE_NEXT: dict[str, str] = {
    "Pending": (
        "Due next: Tasks.Pending → This work item is due for the Tasks stage.\n"
        "Invoke {Stage.Tasks.skill} skill autonomously.\n"
        "UI or task artifact is due; the driver may invoke {Stage.Tasks.skill} directly,\n"
        "and it is possible to continue autonomously."
    ),
    "Review Required": (
        "Due next: Tasks.ReviewRequired → This work item is pending review.\n"
        "Invoke {Stage.Tasks.skill} skill and continue its review procedure.\n"
        "Verify that the work item has been published using `pdlc inspect {ITEM_ID}` and pass\n"
        "its content to the review."
    ),
    "Changes Required": (
        "Due next: Tasks.ChangesRequired → This work item needs changes.\n"
        "User has requested changes. Inspect the open changes below. If the required changes are clear,\n"
        "invoke {Stage.Tasks.skill} and continue to write the delivery tasks. If not, ask the user\n"
        "what changes are needed. Provide context to the user about this work item, since they might\n"
        "not understand what we are working on."
    ),
    "Decision Required": (
        "Due next: Tasks.DecisionRequired → This work item is pending user decision.\n"
        "Inspect the evidence section below, inform the user of the decision required, and record their\n"
        "choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about\n"
        "arguments to pass. Call `pdlc guide decisions` for information about how to handle user\n"
        "decision recording."
    ),
    "CI Pending": (
        "Due next: Tasks.CIPending → We do not stop for CI at this stage.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Approval Required": (
        "Due next: Tasks.ApprovalRequired → This work item is pending user approval.\n"
        "Explicit user approval is required. You are not able to continue autonomously.\n"
        "Ask the user to approve.\n"
        "If user requests changes, follow the re-author procedure specified in the skill, or if approves call `pdlc post approve`.\n"
        "Use `pdlc post approve --help` for more information about arguments to pass."
    ),
    "Approved": (
        "Due next: Tasks.Approved → This work item has been approved to continue.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Stale": (
        "Due next: Tasks.Stale → This work item has been invalidated.\n"
        "User has invalidated the content generated by the work item. Treat this as rewriting Tasks.\n"
        "Invoke {Stage.Tasks.skill} skill and continue its reauthoring procedure. Inspect the open changes\n"
        "below to determine the required changes. If they are not clear or if PDLC was unable to provide\n"
        "them, stop and ask the user."
    ),
}

_TECHNICAL_PLAN_DUE_NEXT: dict[str, str] = {
    "Pending": (
        "Due next: TechnicalPlan.Pending → This work item is due for the Technical Plan stage.\n"
        "Invoke {Stage.TechnicalPlan.skill} skill and continue with instructions specified there."
    ),
    "Review Required": (
        "Due next: TechnicalPlan.ReviewRequired → This work item is pending review.\n"
        "Invoke {Stage.TechnicalPlan.skill} skill and continue its review procedure.\n"
        "Verify that the technical plan for all tasks in the work item have been published using\n"
        "`pdlc inspect task {TASK_IDs}` and pass that content to the review."
    ),
    "Changes Required": (
        "Due next: TechnicalPlan.ChangesRequired → This work item needs changes.\n"
        "User has requested changes. Inspect the open changes below. If the required changes are clear,\n"
        "invoke {Stage.TechnicalPlan.skill} and continue to write the technical plan. If not, ask the user\n"
        "what changes are needed. Provide context to the user about this work item, since they might\n"
        "not understand what we are working on."
    ),
    "Decision Required": (
        "Due next: TechnicalPlan.DecisionRequired → This work item is pending user decision.\n"
        "Inspect the evidence section below, inform the user of the decision required, and record their\n"
        "choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about\n"
        "arguments to pass. Call `pdlc guide decisions` for information about how to handle user\n"
        "decision recording."
    ),
    "CI Pending": (
        "Due next: TechnicalPlan.CIPending → We do not stop for CI at this stage.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Approval Required": (
        "Due next: TechnicalPlan.ApprovalRequired → This work item is pending user approval.\n"
        "Explicit user approval is required. You are not able to continue autonomously.\n"
        "Ask the user to approve.\n"
        "If user requests changes, follow the re-author procedure specified in the skill, or if approves call `pdlc post approve`.\n"
        "Use `pdlc post approve --help` for more information about arguments to pass."
    ),
    "Approved": (
        "Due next: TechnicalPlan.Approved → This work item has been approved to continue.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Stale": (
        "Due next: TechnicalPlan.Stale → This work item has been invalidated.\n"
        "User has invalidated the content generated by the work item. Treat this as rewriting the technical plan.\n"
        "Invoke {Stage.TechnicalPlan.skill} skill and continue its reauthoring procedure. Inspect the open changes\n"
        "below to determine the required changes. If they are not clear or if PDLC was unable to provide\n"
        "them, stop and ask the user."
    ),
}

# Implementation is fully curated, same as Product/UI/Tasks/Technical Plan,
# with two genuine differences from that shape: Pending/Changes Required/Stale
# point at the next eligible delivery task the same way Technical Plan does
# (`_IMPLEMENTATION_NEXT_TASK_GATES`), and Review Required invokes
# `{REVIEW_SKILL}` (the generic pdlc-review dispatcher) rather than the
# stage's own owning skill, since Implementation is reviewed by that
# dispatcher instead of re-entering pdlc-implement — see `pdlc-review/SKILL.md`.
_IMPLEMENTATION_DUE_NEXT: dict[str, str] = {
    "Pending": (
        "Due next: Implementation.Pending → This work item is due for the Implementation stage.\n"
        "Invoke {Stage.Implementation.skill} skill and continue with instructions specified there."
    ),
    "Review Required": (
        "Due next: Implementation.ReviewRequired → This work item is pending review.\n"
        "Invoke {REVIEW_SKILL} skill with this work item's number. Pass the correct scope.\n"
        "Default scope is every task delivered in the current publication pass;\n"
        "if the user named a specific task or asked for a full audit, carry that scope into the\n"
        "dispatch instead of the default."
    ),
    "Changes Required": (
        "Due next: Implementation.ChangesRequired → This work item needs changes.\n"
        "User has requested changes. Inspect the open changes below. If the required changes are clear,\n"
        "invoke {Stage.Implementation.skill} and continue implementing the next eligible delivery task. If not, ask\n"
        "the user what changes are needed. Provide context to the user about this work item, since they might\n"
        "not understand what we are working on."
    ),
    "CI Pending": (
        "Due next: Implementation.CIPending → This work item is pending CI build.\n"
        "Call `pdlc post ci {ITEM_ID} --wait` to monitor and resolve the CI gates; do not use internal gh cli directly as it doesn't configure the pdlc state after CI failure. Act on the instructions provided by that command."
    ),
    "Decision Required": (
        "Due next: Implementation.DecisionRequired → This work item is pending user decision.\n"
        "Inspect the evidence section below, inform the user of the decision required, and record their\n"
        "choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about\n"
        "arguments to pass. Call `pdlc guide decisions` for information about how to handle user\n"
        "decision recording."
    ),
    "Approval Required": (
        "Due next: Implementation.ApprovalRequired → This work item is pending user approval.\n"
        "Explicit user approval is required. You are not able to continue autonomously.\n"
        "Ask the user to approve, or if the approval has been provided call `pdlc post approve`.\n"
        "Use `pdlc post approve --help` for more information about arguments to pass."
    ),
    "Approved": (
        "Due next: Implementation.Approved → This work item has been approved to continue.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Stale": (
        "Due next: Implementation.Stale → This work item has been invalidated.\n"
        "User has invalidated one or more delivery tasks' implementation. `pdlc post invalidate` reopens\n"
        "those tasks specifically (`--task`), the same task-scoped invalidation Technical Plan uses.\n"
        "Invoke {Stage.Implementation.skill} skill and continue implementing the reopened task(s). Inspect\n"
        "the open changes below to determine the required changes. If they are not clear or if PDLC was unable\n"
        "to provide them, stop and ask the user."
    ),
}

# Testing is fully curated too, with the same two kinds of genuine difference
# as Implementation: Pending/Changes Required/Stale end with a `### Testable
# Scope` section instead of a task pointer (Testing is not task-scoped —
# `TASK_SCOPED_STAGES` in `internal/invalidation.py` names only Technical Plan
# and Implementation), and Review Required invokes `{REVIEW_SKILL}` for the
# same dispatcher-not-owning-skill reason as Implementation's, minus its
# depth-scoping paragraph since a Testing review always covers the whole
# artifact (`pdlc-review/SKILL.md`: "Only an Implementation review takes a
# depth").
_TESTING_DUE_NEXT: dict[str, str] = {
    "Pending": (
        "Due next: Testing.Pending → This work item is due for the Testing stage.\n"
        "Invoke {Stage.Testing.skill} skill and continue with instructions specified there."
    ),
    "Review Required": (
        "Due next: Testing.ReviewRequired → This work item is pending review.\n"
        "Invoke {REVIEW_SKILL} skill with this work item's number."
    ),
    "Changes Required": (
        "Due next: Testing.ChangesRequired → This work item needs changes.\n"
        "Inspect the open changes below. If the required changes are clear,\n"
        "invoke {Stage.Testing.skill} and continue writing acceptance coverage. If not, ask\n"
        "the user what changes are needed. Provide context to the user about this work item, since they might\n"
        "not understand what we are working on."
    ),
    "Decision Required": (
        "Due next: Testing.DecisionRequired → This work item is pending user decision.\n"
        "Inspect the evidence section below, inform the user of the decision required, and record their\n"
        "choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about\n"
        "arguments to pass. Call `pdlc guide decisions` for information about how to handle user\n"
        "decision recording."
    ),
    "CI Pending": (
        "Due next: Testing.CIPending → This work item is pending CI build.\n"
        "Call `pdlc post ci {ITEM_ID} --wait` to monitor and resolve the CI gates; do not use internal gh cli directly as it doesn't configure the pdlc state after CI failure. Act on the instructions provided by that command."
    ),
    "Approval Required": (
        "Due next: Testing.ApprovalRequired → This work item is pending user approval.\n"
        "Explicit user approval is required. You are not able to continue autonomously.\n"
        "Ask the user to approve, or if the approval has been provided call `pdlc post approve`.\n"
        "Use `pdlc post approve --help` for more information about arguments to pass."
    ),
    "Approved": (
        "Due next: Testing.Approved → This work item has been approved to continue.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Stale": (
        "Due next: Testing.Stale → This work item has been invalidated.\n"
        "User has invalidated this work item's testing artifact. Invoke {Stage.Testing.skill} skill\n"
        "and continue writing acceptance coverage for the required changes.\n"
        "Inspect the open changes below to determine what changed. If they are not clear or if PDLC was\n"
        "unable to provide them, stop and ask the user."
    ),
}

# Verification is not task-scoped (no Next Pending Task/Testable Scope block)
# and has two genuine differences from every stage before it: it has no
# persisted review policy, so a stray Review Required heals to CI Pending,
# where a clean run lands (`Pipeline.heal()`), instead of dispatching a review; and
# its Approval Required calls out `pdlc post complete`, not `pdlc post
# approve`, since approving here is the completion boundary.
_VERIFICATION_DUE_NEXT: dict[str, str] = {
    "Pending": (
        "Due next: Verification.Pending → This work item is due for the Verification stage.\n"
        "Invoke {Stage.Verification.skill} skill and continue with instructions specified there."
    ),
    "Review Required": (
        "Due next: Verification.ReviewRequired → This stage does not require any additional reviewing.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Changes Required": (
        "Due next: Verification.ChangesRequired → This work item needs changes.\n"
        "Inspect the open changes below. If the required changes are clear,\n"
        "invoke {Stage.Verification.skill} and continue re-verifying the required scope. If not, ask\n"
        "the user what changes are needed. Provide context to the user about this work item, since they might\n"
        "not understand what we are working on."
    ),
    "Decision Required": (
        "Due next: Verification.DecisionRequired → This work item is pending user decision.\n"
        "Inspect the evidence section below, inform the user of the decision required, and record their\n"
        "choice using `pdlc post decision`. Use `pdlc post decision --help` for more information about\n"
        "arguments to pass. Call `pdlc guide decisions` for information about how to handle user\n"
        "decision recording."
    ),
    "CI Pending": (
        "Due next: Verification.CIPending → This work item is pending CI build.\n"
        "Call `pdlc post ci {ITEM_ID} --wait` to monitor and resolve the CI gates; do not use internal gh cli directly as it doesn't configure the pdlc state after CI failure. Act on the instructions provided by that command."
    ),
    "Approval Required": (
        "Due next: Verification.ApprovalRequired → This work item is pending user approval.\n"
        "Explicit user approval is required. You are not able to continue autonomously.\n"
        "Ask the user to approve, or if the approval has been provided call `pdlc post complete`.\n"
        "Use `pdlc post complete --help` for more information about arguments to pass."
    ),
    "Approved": (
        "Due next: Verification.Approved → This work item has been approved to continue.\n"
        "Call `pdlc next {ITEM_ID}` to continue this work item."
    ),
    "Stale": (
        "Due next: Verification.Stale → This work item has been invalidated.\n"
        "User has invalidated this work item's verification. Invoke {Stage.Verification.skill} skill\n"
        "and continue re-verifying the required scope. Inspect the open changes below to determine what\n"
        "changed. If they are not clear or if PDLC was unable to provide them, stop and ask the user."
    ),
}

# One dict per stage that has its own per-gate Due Next text, keyed by stage
# name (`due_next()["status"]`) to look up which table applies. Every active
# Feature-pipeline stage is now fully curated, all 8 gates.
_STAGE_DUE_NEXT: dict[str, dict[str, str]] = {
    "Product": _PRODUCT_DUE_NEXT,
    "UI": _UI_DUE_NEXT,
    "Tasks": _TASKS_DUE_NEXT,
    "Technical Plan": _TECHNICAL_PLAN_DUE_NEXT,
    "Implementation": _IMPLEMENTATION_DUE_NEXT,
    "Testing": _TESTING_DUE_NEXT,
    "Verification": _VERIFICATION_DUE_NEXT,
}

# `due_next()` only returns a `skill` for gates its routing hands to a skill
# (e.g. Decision Required routes to a human, with no `skill`, even though that
# gate's curated text below names the stage's skill) — read the stage's `skill`
# directly instead so the `{Stage.<name>.skill}` substitution always has a
# value to work with.
_STAGE_SKILL: dict[str, str] = {
    "Product": PRODUCT_STAGE.skill or "",
    "UI": UI_STAGE.skill or "",
    "Tasks": TASKS_STAGE.skill or "",
    "Technical Plan": TECHNICAL_PLAN_STAGE.skill or "",
    "Implementation": IMPLEMENTATION_STAGE.skill or "",
    "Testing": TESTING_STAGE.skill or "",
    "Verification": VERIFICATION_STAGE.skill or "",
}

# Changes Required, Stale, and Decision Required are the gates whose cause
# lives in evidence comments rather than being implied by the gate itself.
# Changes Required (review findings, a Verification bounce, a CI failure, a
# resolved decision) and Stale (a driver invalidation or a bounce) can each
# have more than one cause outstanding, so `_due_next_section` summarises every
# change request the stage has not addressed since it last published under
# `### Open Changes` and points at `pdlc inspect changes` for their text.
# Decision Required has one blocking question, so it inlines the newest
# PDLC-DECISION comment under `### Evidence`.
_OPEN_CHANGES_GATES = ("Changes Required", "Stale")
_DECISION_MARKERS = ("DECISION",)

# What each evidence gate's fallback prose calls the missing evidence, so
# "required changes" isn't misapplied to a Decision Required gate.
_EVIDENCE_NOUN: dict[str, str] = {
    "Changes Required": "changes",
    "Stale": "changes",
    "Decision Required": "decision",
}


def _no_evidence_fallback(gate: str) -> str:
    """Folded directly into the Due Next body (no evidence heading) when no
    open change request or decision comment is found at all, so an agent never
    mistakes silence for a confirmed absence of required changes/decision."""
    return (
        f"PDLC was unable to parse and identify any evidence for the required {_EVIDENCE_NOUN[gate]}.\n"
        "Inspect the timeline (`pdlc inspect timeline {ITEM_ID}`) to see if this is clear\n"
        "in the conversation so far. Read the user's comments on the work item\n"
        "(`pdlc inspect comments {ITEM_ID}`) to gather more evidence. Stop and request\n"
        "the user's confirmation before continuing. Do not assume anything — this work\n"
        "item is no longer able to continue autonomously."
    )


def _evidence_block(item: dict, comments: list[dict], stage: str, gate: str) -> str | None:
    """The `### Open Changes` or `### Evidence` block for an evidence gate, or
    None when there is nothing to show and the fallback applies."""
    if gate in _OPEN_CHANGES_GATES:
        changes = open_change_requests(comments, pipeline_for_item(item), stage)
        if not changes.requests:
            return None
        return (
            f"### Open Changes\n\n{open_changes_summary(changes)}\n"
            "Run `pdlc inspect changes {ITEM_ID}` for their full text, and address every one of them."
        )
    comment = latest_marked_comment(comments, _DECISION_MARKERS)
    if comment is None:
        return None
    when = timeline_formatted_at(comment["createdAt"])
    return (
        f"### Evidence\n\nThis evidence was posted at {when}.\n{evidence_comment_text(comment)}\n\n"
        "Call `pdlc inspect timeline {ITEM_ID}` for the full timeline context of this work item."
    )

# Technical Plan and Implementation are task-scoped: these are the gates
# where "which task still needs work" is actually informative. The others are
# record-level states reached only once every task's plan/implementation is
# already done, so a "next pending task" pointer there would almost always
# read "none" and add nothing. Testing is not task-scoped the same way — there
# is no single "next eligible task" (`TASK_SCOPED_STAGES` in
# `internal/invalidation.py` names only these two) — so its equivalent gates
# point at the always-runnable `pdlc inspect test` instead; see
# `_TESTABLE_SCOPE_GATES` below.
_TECHNICAL_PLAN_NEXT_TASK_GATES = ("Pending", "Changes Required", "Stale")
_IMPLEMENTATION_NEXT_TASK_GATES = ("Pending", "Changes Required", "Stale")


def _next_plan_task_line(tasks: list[dict]) -> str:
    for task in tasks:
        if task["needsPlan"]:
            number = task["number"]
            return (
                f"The next task pending a Technical Plan is {number}. "
                f"Call `pdlc inspect task {number}` for its current content, and "
                f"`pdlc inspect task timeline {number}` for its evidence history."
            )
    return "No delivery tasks are currently pending a Technical Plan."


def _next_implementation_task_line(tasks: list[dict]) -> str:
    eligible = sorted(
        (t for t in tasks if t["state"] == "OPEN" and t["hasPlan"] and (not t["hasImplementation"] or t["implementationInvalidated"])),
        key=lambda t: (t["isUI"], t["number"]),
    )
    if eligible:
        number = eligible[0]["number"]
        return (
            f"The next task pending implementation is {number}. "
            f"Call `pdlc inspect task {number}` for its current content, and "
            f"`pdlc inspect task timeline {number}` for its evidence history."
        )
    return "No delivery tasks are currently pending implementation."


_NEXT_TASK_GATES: dict[str, tuple[str, ...]] = {
    "Technical Plan": _TECHNICAL_PLAN_NEXT_TASK_GATES,
    "Implementation": _IMPLEMENTATION_NEXT_TASK_GATES,
}
_NEXT_TASK_LINE = {
    "Technical Plan": _next_plan_task_line,
    "Implementation": _next_implementation_task_line,
}

# Testing's task-agnostic equivalent of `### Next Pending Task`: the same
# three record-level gates, pointing at the real, always-runnable
# `pdlc inspect test {ITEM_ID}`, which reports every delivery task closed
# with its implementation recorded, its linked PRs, and the files those PRs
# touched.
_TESTABLE_SCOPE_GATES = ("Pending", "Changes Required", "Stale")
_TESTABLE_SCOPE_BLOCK = (
    "### Testable Scope\n\n"
    "Call `pdlc inspect test {ITEM_ID}` for the current testable scope: every delivery task closed\n"
    "with its implementation recorded, its linked PRs, and the files those PRs touched."
)


def _patches_block(comments: list[dict]) -> str | None:
    """`### Patches Since Last Approval` at an Approval Required gate: the
    upstream artifacts corrected in place that the driver has not approved
    past yet, or None when there are none."""
    patches = patches_since_approval(comments)
    if not patches:
        return None
    lines = []
    for patch in patches:
        line = f"- {patch['patchedStage']} — {timeline_formatted_at(patch['createdAt'])}: {patch.get('url') or 'no url'}"
        if patch["changedRequirements"]:
            line += f"\n  - Changed requirements: {patch['changedRequirements']}"
        lines.append(line)
    return (
        "### Patches Since Last Approval\n\n"
        "These upstream artifacts were corrected in place since the last approval. Show them to the user\n"
        "before asking for approval, with the before and after text of every changed requirement;\n"
        "`pdlc inspect timeline {ITEM_ID}` has each patch's requirement changes and impact report.\n\n"
        + "\n".join(lines)
    )


def _due_next_section(item: dict, comments: list[dict], tasks: list[dict]) -> str:
    due = due_next(item)
    item_id = item_issue(item)
    if due["state"] == "Uninitialized":
        return "# Due Next\n\nDue next: Uninitialized → pdlc-write"
    if due["status"] == "Complete":
        return "# Due Next\n\nThis work item has been completed."
    stage_due_next = _STAGE_DUE_NEXT.get(due["status"])
    # A blocked route (e.g. an unknown or unavailable work type on an otherwise
    # well-formed Feature stage/gate) must not render that stage's curated work text.
    if stage_due_next is not None and due["gate"] in stage_due_next and due["action"] != "blocked":
        skill = _STAGE_SKILL.get(due["status"], "")
        # The placeholder spells the stage without spaces (`{Stage.TechnicalPlan.skill}`).
        placeholder = f"{{Stage.{due['status'].replace(' ', '')}.skill}}"
        default_body = stage_due_next[due["gate"]].replace(placeholder, skill)
        if "{REVIEW_SKILL}" in default_body:
            default_body = default_body.replace("{REVIEW_SKILL}", due["action"])
        if due["status"] == "Technical Plan" and due["gate"] == "Review Required":
            task_ids = ", ".join(str(task["number"]) for task in tasks)
            default_body = default_body.replace("{TASK_IDs}", task_ids)
        next_task_block = None
        if due["gate"] in _NEXT_TASK_GATES.get(due["status"], ()):
            next_task_block = "### Next Pending Task\n\n" + _NEXT_TASK_LINE[due["status"]](tasks)
        elif due["status"] == "Testing" and due["gate"] in _TESTABLE_SCOPE_GATES:
            next_task_block = _TESTABLE_SCOPE_BLOCK
        elif due["gate"] == "Approval Required":
            next_task_block = _patches_block(comments)
        if due["gate"] not in _EVIDENCE_NOUN:
            body = default_body if next_task_block is None else default_body + "\n\n" + next_task_block
            return ("# Due Next\n\n" + body).replace("{ITEM_ID}", item_id)
        evidence_block = _evidence_block(item, comments, due["status"], due["gate"])
        if evidence_block is None:
            header = default_body.split("\n", 1)[0]
            body = header + "\n" + _no_evidence_fallback(due["gate"])
            if next_task_block is not None:
                body += "\n\n" + next_task_block
            return ("# Due Next\n\n" + body).replace("{ITEM_ID}", item_id)
        body = default_body if next_task_block is None else default_body + "\n\n" + next_task_block
        body += "\n\n" + evidence_block
        return ("# Due Next\n\n" + body).replace("{ITEM_ID}", item_id)
    # Reachable only for a status/gate combination `due_next()` cannot parse or
    # heal (a malformed or unsupported work item state) — every real stage
    # name curates all eight gates above, and Complete returns early.
    return (
        f"# Due Next\n\nDue next: {due['state']} → {due.get('owner', due['action'])}\n"
        f"{due['reason'].capitalize()}."
    )


def due_next_section(item: dict) -> tuple[str, bool]:
    """The `# Due Next` section `pdlc inspect` renders for an already-resolved
    record, fetching its comments and task tree. `pdlc next` prints this same
    section for the record it routes, so both commands give one instruction.

    The flag is True when the section is an evidence gate's no-evidence
    fallback, which tells the agent to stop for the user's confirmation — the
    caller must not then report the record as autonomous work."""
    comments, tasks = comments_and_tasks(item_issue(item))
    section = _due_next_section(item, comments, tasks)
    due = due_next(item)
    unevidenced = (
        due["status"] in _STAGE_DUE_NEXT
        and due["gate"] in _EVIDENCE_NOUN
        and due["action"] != "blocked"
        and _evidence_block(item, comments, due["status"], due["gate"]) is None
    )
    return section, unevidenced


def _warnings_section(item: dict, comments: list[dict], pull_requests: list[dict]) -> str | None:
    """`# Warnings`: each way the record's gate claims more than its evidence
    shows (`evidence_warnings`), or None when they agree. A stage declared in
    Skipped States publishes nothing, so it has nothing to disagree with."""
    try:
        pipeline = pipeline_for_item(item)
        status = item_status(item)
        lifecycle = item.get("Lifecycle") or (Lifecycle.COMPLETED if status == pipeline.terminal_stage else Lifecycle.PLANNING)
        state = State.parse(status, item_gate(item), lifecycle)
    except (PdlcError, TypeError, ValueError):
        return None
    if is_stage_skipped(item, state.stage):
        return None
    warnings = evidence_warnings(comments, pipeline, state, has_pull_requests=bool(pull_requests))
    if not warnings:
        return None
    return (
        "# Warnings\n\n"
        "The Gate State claims more than this work item's evidence shows. `# Due Next` still routes on the gate;\n"
        "report each warning to the driver rather than working around it.\n\n"
        + "\n".join(f"- {warning}" for warning in warnings)
    )


def _task_front_matter(task: dict) -> str:
    return yaml_front_matter({
        "number": task["number"],
        "title": task["title"],
        "completed": task["state"] == "CLOSED",
        "isUI": task["isUI"],
        "hasPlan": task["hasPlan"],
        "hasImplementation": task["hasImplementation"],
        "implementationInvalidated": task["implementationInvalidated"],
        "needsPlan": task["needsPlan"],
    })


def _compact_pull_request(pr: dict) -> dict:
    return {
        key: pr[key]
        for key in ("number", "url", "state", "checks")
        if key in pr
    }


def _compact_metadata(item: dict, pull_requests: list[dict]) -> str:
    return yaml_front_matter({
        "id": item["id"],
        "content": item["content"],
        "Status": item.get("Status"),
        "Gate State": item.get("Gate State"),
        "Lifecycle": item.get("Lifecycle"),
        "workType": item.get("workType") or "feature",
        "Skipped States": item_skipped_states(item),
        "pullRequests": [_compact_pull_request(pr) for pr in pull_requests],
    })


def _body_location(full_output: str, body: str, path: Path, heading: str) -> str:
    if not body:
        return f"Full inspection in {path}; the work item body is empty."

    lines = full_output.splitlines()
    # The work-item heading, blank line, then the body; the section that follows
    # (Attachments) is not relied on for the span.
    start = lines.index(heading) + 3
    end = start + len(body.splitlines()) - 1
    return f"Full inspection in {path}; read lines {start}-{end} for the body."


def _compact_render(
    item: dict,
    pull_requests: list[dict],
    tasks: list[dict],
    attachments: list[dict],
    user_comments_section: str,
    full_output: str,
    path: Path,
    due_next_section: str,
    warnings_section: str | None = None,
) -> str:
    body = (item.get("issueBody") or "").rstrip("\n")
    uninitialized = due_next(item)["state"] == "Uninitialized"
    sections = [_compact_metadata(item, pull_requests)]
    if uninitialized:
        sections.append(f"# Requirements\n\n{body}")
    else:
        sections.append(f"# Work Item\n\n{_body_location(full_output, body, path, '# Work Item')}")
    sections.append(attachments_markdown(attachments))
    sections.append(user_comments_section)

    if not tasks:
        sections.append("# Tasks\n\nNo Tasks")
    else:
        task_blocks = "\n\n".join(_task_front_matter(task) for task in tasks)
        sections.append(f"# Tasks\n\n{task_blocks}")

    if warnings_section is not None:
        sections.append(warnings_section)
    sections.append(due_next_section)
    return "\n\n".join(sections) + "\n"


def render(issue: str) -> tuple[str, str, Path]:
    # One comment fetch feeds the `## User Comments` section in both renders.
    item, tasks, comments = record_snapshot(issue)
    pull_requests = record_pull_requests(issue, record=item, tasks=tasks)
    attachments = attachments_for_item(item)

    metadata = {
        "id": item["id"],
        "content": item["content"],
        "Status": item.get("Status"),
        "Gate State": item.get("Gate State"),
        "Lifecycle": item.get("Lifecycle"),
        "workType": item.get("workType") or "feature",
        "Skipped States": item_skipped_states(item),
        "pullRequests": pull_requests,
    }

    user_comments_section = user_comments_markdown(issue, comments=comments)
    comments_notice = older_comments_notice(issue, item.get("commentsMeta"), len(comments))
    if comments_notice:
        user_comments_section += f"\n\n> Older comments are omitted from this view. {comments_notice}."

    body = (item.get("issueBody") or "").rstrip("\n")
    uninitialized = due_next(item)["state"] == "Uninitialized"

    sections = [yaml_front_matter(metadata)]
    sections.append(f"# {'Requirements' if uninitialized else 'Work Item'}\n\n{body}")
    sections.append(attachments_markdown(attachments))
    sections.append(user_comments_section)

    if not tasks:
        sections.append("# Tasks\n\nNo Tasks")
    else:
        task_blocks = "\n\n".join(_task_front_matter(task) for task in tasks)
        sections.append(f"# Tasks\n\n{task_blocks}")

    warnings_section = _warnings_section(item, comments, pull_requests)
    if warnings_section is not None:
        sections.append(warnings_section)
    due_next_section = _due_next_section(item, comments, tasks)
    sections.append(due_next_section)

    full_output = "\n\n".join(sections) + "\n"
    path = scratch_path(str(issue), str(issue))
    compact_output = _compact_render(
        item, pull_requests, tasks, attachments, user_comments_section, full_output, path, due_next_section, warnings_section
    )
    return full_output, compact_output, path


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="Inspect a PDLC work item")
    parser.add_argument("work_item")
    parser.add_argument(
        "--full", action="store_true",
        help="print the complete inspection to stdout",
    )
    parser.add_argument(
        "--file", action="store_true",
        help="write to the configured work-item cache and print that path instead of stdout",
    )
    args = parser.parse_args(command_args)

    if args.full and args.file:
        parser.error("--full and --file cannot be used together")

    try:
        full_output, compact_output, path = render(args.work_item)
    except PdlcError as error:
        return report_failure(error)

    if args.file:
        print(write_scratch(path, full_output))
    elif args.full:
        sys.stdout.write(full_output)
    else:
        write_scratch(path, full_output)
        sys.stdout.write(compact_output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
