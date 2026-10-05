#!/usr/bin/env python3
"""NAME
    pdlc post complete - final transition: lock a verified record to Complete

USAGE
    pdlc post complete WORK_ITEM EVIDENCE_FILE|- [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --attachment PATH (repeatable)      attach a local file's contents to the completion evidence
    --attachment-description TEXT       description for the --attachment immediately before it

DESCRIPTION
    Locks a verified record to Complete: validates the structured completion
    evidence, posts it, locks Status/Gate/Lifecycle to
    Complete/Approved/Completed, blanks the now-settled `## Open
    Questions` section (its real disposition lives in the evidence), and
    closes the record on its host. It never otherwise edits the parent body.

    Closing the record means a closed GitHub Issue, or on Azure the
    configured `[tracker.azure] closed_state` (default `Done`) written to
    the work item's own state.

    Once the record is locked and closed, it prunes local branches on a
    best-effort basis: each merged PR's local branch is force-deleted only
    when its tip still equals the PR's head commit. If HEAD is on such a
    branch and the working tree is clean, it first switches to the local
    default branch, or detaches at the remote default when that branch is
    checked out elsewhere. Only local branches are touched; a branch that
    cannot be deleted is reported, never fatal.

    This is a final transition: only from Verification / Approval Required,
    only on explicit human instruction, and only once completion blockers
    are empty. Only the orchestrator may call this — this is a procedural
    boundary, not an authentication check, since identity cannot
    distinguish a human from an agent acting on their behalf.

EVIDENCE_FILE holds six `##` sections, in any order, each non-empty:

  - Shipped — the scope delivered: tasks, PRs, what a user can now do.
  - Verification — must state `clean @ <commit>`, plus a one-line outcome.
  - Decisions — decisions that emerged during delivery, one bullet each
    with rationale and reference.
  - Open Questions — one bullet per live entry in the record's Open
    Questions section: `<question> — Resolved: <answer>` or
    `<question> — Deferred: <what>, tracked as <ref>`. A body that leaves
    any live entry unaccounted for is refused.
  - Limitations — known limitations or deferrals carried into release.
  - Skipped Stages — each skipped stage, noted as a deliberate bypass.

Decisions, Open Questions, Limitations, and Skipped Stages are a bulleted
list, or a lone `- None` when there is nothing to record. For example:

    ## Shipped

    Offline tile pinning across 7 tasks, PRs #144-#153, all merged.

    ## Verification

    clean @ a1b2c3d — claims, 4 journeys, UX reviewed, cumulative review clean.

    ## Decisions

    - Evict pinned tiles LRU once the regional cap is hit — simpler than a manual queue (WORK-142-TASK-004).

    ## Open Questions

    - Should tile eviction be LRU or manual-only? — Resolved: LRU, capped per region.
    - Do we cap pinned regions at five? — Deferred: revisit for the paid tier, tracked as #210.

    ## Limitations

    - Pre-existing profile migration deferred to a follow-up record.

    ## Skipped Stages

    - None

On success the command prints JSON with `completed: true` and a
`branches` object: `deleted` (branch names) and `skipped` (`{branch,
reason}` with reason `missing`, `sha-unknown`, `sha-mismatch`,
`dirty-tree`, `switch-failed`, `checked-out-elsewhere`, `delete-failed`,
or `git-unavailable`).
"""

from __future__ import annotations

import json
import sys


from pdlc.internal.pull_requests import record_pull_requests
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number
from pdlc.domain.completion import completion_blockers
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import resolve_text, print_help, wants_help
from pdlc.domain.workflow import Event, decision_required_message
from pdlc.internal.verification import verification_state
from pdlc.internal.worktree import prune_merged_branches
from pdlc.internal.workitem import (
    comments_for_issue,
    close_record,
    item_for_issue,
    item_gate,
    item_skipped_states,
    item_status,
    marked_comments,
    post_comment,
    read_section,
    set_state,
    task_tree,
    update_section,
    workflow_for_item,
)
from pdlc.internal.failure import Recovery, report_failure, set_recovery

OPEN_QUESTIONS_SETTLED = "_Resolved at completion — see the completion comment._"


def complete(issue: str, evidence: str, attachment_inputs: list[dict]) -> dict:
    evidence_body = resolve_text(evidence, label="completion evidence")

    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)
    if item_gate(record) == "Decision Required":
        raise PdlcError(decision_required_message(item_status(record)))
    body = record.get("issueBody") or ""
    comments = comments_for_issue(issue)

    tasks = task_tree(issue)
    pull_requests = record_pull_requests(issue, record=record, tasks=tasks)
    verification_body, _, stale_rows, open_findings = verification_state(issue, comments, tasks)
    blockers = completion_blockers(
        pipeline=pipeline,
        status=item_status(record),
        gate=item_gate(record),
        tasks=tasks,
        pull_requests=pull_requests,
        timeline_markers=[comment["marker"] for comment in marked_comments(issue, comments=comments)],
        skipped_states=item_skipped_states(record),
        verification_body=verification_body,
        stale_rows=stale_rows,
        open_findings=open_findings,
        open_questions=read_section(body, "Open Questions"),
        evidence_body=evidence_body,
    )
    if blockers:
        raise PdlcError(
            "record is not ready to complete:\n"
            + "\n".join(f"  - [{blocker.code}] {blocker.message}" for blocker in blockers)
        )
    try:
        target = pipeline.next_state(state, Event.COMPLETED)
    except ValueError as error:
        raise PdlcError(str(error)) from None

    attachments = save_attachments(work_item_number(record), attachment_inputs)
    post_comment(issue, evidence_body, "COMPLETE")
    set_state(record["id"], target.stage, target.gate.value, target.lifecycle.value)
    update_section(issue, "Open Questions", OPEN_QUESTIONS_SETTLED)
    close_record(issue)
    branches = prune_merged_branches(pull_requests)

    return {
        "completed": True, "itemId": record["id"], "work_item": int(issue),
        "attachments": attachments, "branches": branches,
    }


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw_args = command_args
    if wants_help(raw_args):
        print_help(__doc__)
        return 0
    try:
        args, attachment_inputs = parse_attachment_arguments(raw_args)
    except PdlcError as error:
        return report_failure(error)
    if len(args) != 2:
        print("usage: pdlc post complete WORK_ITEM EVIDENCE_FILE|-", file=sys.stderr)
        return 1
    issue, evidence = args

    try:
        set_recovery(Recovery(
            check=f"pdlc inspect {issue}",
            landed="the stage is Complete",
            then="the record is locked. If it is still open on the host, stop and report that it needs closing there; `pdlc cleanup` removes leftover branches.",
        ))
        result = complete(issue, evidence, attachment_inputs)
    except PdlcError as error:
        return report_failure(error)

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
