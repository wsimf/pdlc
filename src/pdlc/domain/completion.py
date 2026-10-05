"""One completion-readiness policy, shared by `pdlc inspect complete`
(reports the blockers) and `pdlc post complete` (refuses to lock while any
remain), so the inspector and the mutator can never disagree about what
"ready to complete" means.

Pure: every input is data the caller already fetched. `completion_blockers`
returns the full list rather than raising on the first, so a single pass
tells the driver everything still outstanding.
"""

from __future__ import annotations

from dataclasses import dataclass

from pdlc.domain.records import pull_request_label
from pdlc.domain.completion_evidence import parse_completion_report, undispositioned_questions
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.verification import SCHEMA, parse
from pdlc.domain.workflow import Pipeline

SETTLEMENT_MARKERS = {"APPROVED", "AUTOAPPROVED", "SKIPPED"}

@dataclass(frozen=True)
class Blocker:
    code: str
    message: str


def _skipped(skipped_states: str | None) -> set[str]:
    return {state for state in (skipped_states or "").split(",") if state}


def completion_blockers(
    *,
    pipeline: Pipeline,
    status: str,
    gate: str,
    tasks: list[dict],
    pull_requests: list[dict],
    timeline_markers: list[str],
    skipped_states: str | None,
    verification_body: str | None,
    stale_rows: list[str] | None = None,
    open_findings: list[str] | None = None,
    open_questions: str = "",
    evidence_body: str | None = None,
) -> list[Blocker]:
    blockers: list[Blocker] = []
    skipped = _skipped(skipped_states)
    policy = pipeline.completion_policy
    if policy is None:
        return [Blocker("unsupported-work-type", f"No completion policy for work type {pipeline.work_type.value}.")]

    if status == pipeline.terminal_stage:
        return [Blocker("already-complete", "The record is already Complete and locked.")]
    if status != policy.boundary_stage:
        blockers.append(Blocker("status", f"Status is {status or 'unset'!r}, not {policy.boundary_stage}. That stage owns this record now."))
    if gate != policy.boundary_gate.value:
        blockers.append(Blocker("gate", f"Gate State is {gate or 'unset'!r}, not {policy.boundary_gate.value}. {policy.boundary_stage} is unfinished."))

    open_tasks = [task for task in tasks if policy.require_tasks_closed and task.get("state") != "CLOSED"]
    if open_tasks:
        listed = ", ".join(f"#{task['number']} {task.get('title', '').strip()}".rstrip() for task in open_tasks)
        blockers.append(Blocker(
            "open-tasks",
            "Open delivery tasks must leave active scope through a durable defer or descope before completion: " + listed,
        ))

    closed_no_impl = [
        task for task in tasks
        if policy.require_task_implementation and task.get("state") == "CLOSED" and not task.get("hasImplementation")
    ]
    if closed_no_impl:
        listed = ", ".join(f"#{task['number']}" for task in closed_no_impl)
        blockers.append(Blocker(
            "closed-without-implementation",
            f"Closed tasks with no implementation pull request attached: {listed}",
        ))

    unsettled_prs = [
        pr for pr in pull_requests
        if (policy.require_prs_merged and pr.get("state") != "MERGED")
        or (policy.require_checks_green and pr.get("checks") not in ("SUCCESS", "NONE"))
    ]
    if unsettled_prs:
        listed = ", ".join(
            f"{pull_request_label(pr)} {pr.get('state')} checks:{pr.get('checks')}" for pr in unsettled_prs
        )
        blockers.append(Blocker(
            "pull-requests",
            "Every linked closing PR must be merged with passing required checks, "
            f"or explicitly unlinked: {listed}",
        ))

    markers = list(timeline_markers)
    settled_stages = policy.settled_stages(pipeline.active_stage_names, skipped)

    missing_evidence = [
        stage for stage in settled_stages
        if pipeline.marker_for_stage(stage) not in markers
    ]
    if missing_evidence:
        blockers.append(Blocker(
            "stage-evidence",
            f"No stage evidence comment on record for: {', '.join(missing_evidence)}",
        ))

    settlements = sum(1 for marker in markers if marker in SETTLEMENT_MARKERS)
    if policy.require_stage_settlement and settlements < len(settled_stages):
        blockers.append(Blocker(
            "stage-settlement",
            f"Each non-skipped stage needs one settlement marker "
            f"(PDLC-APPROVED, PDLC-AUTOAPPROVED, or PDLC-SKIPPED); "
            f"found {settlements}, expected at least {len(settled_stages)}.",
        ))

    if policy.verification_parser not in (None, SCHEMA):
        blockers.append(Blocker("verification-parser", f"Unsupported verification parser: {policy.verification_parser}."))
    elif policy.verification_parser and verification_body is None:
        blockers.append(Blocker("no-verification", "No Verification review evidence — pdlc-verify must run first."))
    elif policy.verification_parser:
        try:
            parse(verification_body)
        except PdlcError as error:
            blockers.append(Blocker("verification-malformed", f"Verification evidence is not valid: {error}"))

    if open_findings:
        blockers.append(Blocker(
            "verification-findings",
            "Verification findings are still open or awaiting a decision; re-verify: " + "; ".join(open_findings),
        ))

    if stale_rows:
        blockers.append(Blocker(
            "verification-stale",
            "Verification evidence no longer holds against current source; re-verify: "
            + "; ".join(stale_rows),
        ))

    # Completion evidence disposes of each live Open Questions entry as
    # Resolved or Deferred, and the mutator blanks the section afterwards.
    # Nothing to check until that evidence exists (inspection runs first).
    if evidence_body is not None:
        try:
            report = parse_completion_report(evidence_body)
        except PdlcError as error:
            blockers.append(Blocker("evidence-malformed", f"Completion evidence is not valid: {error}"))
        else:
            unaccounted = undispositioned_questions(report, open_questions)
            if unaccounted:
                blockers.append(Blocker(
                    "open-questions",
                    "Live Open Questions entries are not dispositioned (Resolved/Deferred) "
                    "in the completion evidence: " + "; ".join(unaccounted),
                ))

    return blockers
