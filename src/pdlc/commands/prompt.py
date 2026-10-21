#!/usr/bin/env python3
"""NAME
    pdlc prompt - write the ready-to-send brief for a work item's next unit; nothing is published to the backend

USAGE
    pdlc prompt COMMAND WORK_ITEM [flags]

COMMANDS
    task-implementer   brief the sub-agent that writes one delivery task's code
    task-reviewer      brief the reviewer that reads one dispatch's commits
    task-test-writer   brief the test writer that covers one dispatch's change
    acceptance-test-writer  brief the test writer that covers the whole implemented scope
    task-planner       brief the sub-agent that decomposes a record into delivery tasks
    tech-planner       brief the sub-agent that spikes the open delivery tasks into plans
    product-reviewer   brief the reviewer that checks a Product draft before it lands
    ui-planner         brief the sub-agent that authors a record's UI section
    tasks-reviewer     brief the reviewer that checks a UI fragment or Tasks breakdown before it lands
    plan-reviewer      brief the reviewer that checks a pass's delivery-task plans before they land
    cumulative-reviewer  brief the sub-agent running the project's cumulative-review capability
    ui-journey-reviewer  brief the sub-agent walking a record's UI journeys against a fresh build

DESCRIPTION
    Writes one complete sub-agent brief for the unit of work a record has next,
    with every value already filled in, and prints only the brief file's path.
    That file is sent to the sub-agent verbatim: it carries the task, its plan,
    the covered requirements, and the boundaries the agent works inside, and it
    names no PDLC command, stage, or gate.

    The three `task-*` commands describe the same unit, so the implementer,
    the reviewer, and the test writer are held to one task, one plan, and one
    set of acceptance criteria on a given pass. They differ only in what each
    sub-agent needs that the record cannot supply, which is why they take
    different flags. `acceptance-test-writer` describes the whole implemented
    scope once every task has landed, rather than one task. `task-planner`
    describes the record itself, ahead of any delivery task existing, so it
    belongs to the Tasks stage rather than the Implementation loop the other
    four cover. `tech-planner` describes every open delivery task at once,
    ahead of any of them being built.

    `product-reviewer` is the exception to `COMMAND WORK_ITEM`: it reviews a
    Product draft that may exist only as a local scratch file, not yet on any
    record, so it takes the draft's path as its positional argument and the
    record as an optional `--work-item`, omitted entirely for a fresh draft.
    `cumulative-reviewer` is the same kind of exception in the other
    direction: it takes no work item at all, since nothing in its brief comes
    from the record.

    `ui-planner` describes the record itself, ahead of any UI section
    existing, so like `task-planner` it belongs to a stage rather than the
    Implementation loop; unlike the loop briefs it also names the project's
    configured UX-design skill, since a UI section is designed rather than
    implemented from a plan.

    `tasks-reviewer` and `plan-reviewer` review a local, not-yet-landed
    artifact against the parent's own body, the same way `product-reviewer`
    does; `tasks-reviewer` takes at most one of `--manifest` (a Tasks
    breakdown) or `--fragment` (a UI section), since one reviewer checks both
    artifacts. Without one, either reviews the published artifact as it
    stands. `cumulative-reviewer` and `ui-journey-reviewer` brief the two
    sub-agents a Verification pass dispatches; both sub-agents know nothing
    about PDLC, so the record's `FR-*`/`C-*` intent and a one-sentence account
    of what shipped arrive as flags in plain language rather than being
    resolved from the record here — that translation is the caller's
    judgment, not a mechanical fact. `ui-journey-reviewer` still resolves the
    journeys and UX staleness itself, the same carried-forward computation
    `pdlc inspect verify` renders as `## Journeys to review`.

    Nothing due prints what the record is waiting on and exits non-zero, so a
    caller never dispatches an agent against an empty unit. Every command reads
    the record and its live pull-request state; none changes the record, and
    nothing is published to the backend. `task-planner`, `tech-planner`, and
    `ui-planner` may write editable copies to the work-item cache.
    `tasks-reviewer` and `plan-reviewer` record the files they hand
    the reviewer, so the stage lands only what was reviewed; they and the
    matching planner briefs restore a reviewed file that changed since. They
    and `task-reviewer` also write a fresh findings file for the reviewer to
    fill.

    Exit 3 means the brief would hand its agent nothing to do, so none is
    written: the caller skips that dispatch and carries on. Any other non-zero
    exit is a refusal.

    A value the record does not carry is reported in place rather than omitted —
    a cited requirement missing from the record's `## Product` renders as "not
    found" inside the brief instead of leaving the agent a hole it cannot see.

EXAMPLES
    pdlc prompt task-implementer 236
    pdlc prompt task-reviewer 236 --commits HEAD~2..HEAD
    pdlc prompt acceptance-test-writer 236 --traceability /tmp/trace.md
    pdlc prompt task-planner 236
    pdlc prompt tech-planner 236
    pdlc prompt product-reviewer /tmp/pdlc-route-shape-detection-body.md
    pdlc prompt ui-planner 236
    pdlc prompt tasks-reviewer 236 --manifest /tmp/pdlc-tasks.json
    pdlc prompt plan-reviewer 236 --manifest /tmp/pdlc-plan.json
    pdlc prompt cumulative-reviewer --shipped text:"..." --unchanged text:"..." --constraints text:"..."
    pdlc prompt ui-journey-reviewer 236 --description text:"offline route retry"

LEARN MORE
    Run `pdlc prompt COMMAND --help` for that command's own usage and flags.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pdlc.domain.records import PullRef, pull_request_label
from pdlc.commands.inspect_capability import _name as capability_name
from pdlc.commands.inspect_capability import _one as capability_line
from pdlc.commands.inspect_test import readiness as testing_readiness
from pdlc.commands.inspect_test import testable_scope
from pdlc.config import get_capabilities, get_config
from pdlc.domain.changes import ChangeRequest, open_change_requests, upstream_changes
from pdlc.domain.plan_file import (
    manifest_errors,
    parse as parse_plan_file,
    plan_baseline,
    planner_command as plan_planner_command,
    regenerate,
    render as render_plan_file,
    reviewer_command as plan_reviewer_command,
    same_plan,
    stored_plan,
)
from pdlc.domain.task_artifact import planner_command as tasks_planner_command
from pdlc.domain.task_artifact import reviewer_command as tasks_reviewer_command
from pdlc.domain.task_artifact import ui_planner_command, ui_reviewer_command
from pdlc.domain.task_artifact import snapshot, stored_fields
from pdlc.domain.implement_findings import ImplementFindings
from pdlc.domain.implement_findings import parse as parse_implement_findings
from pdlc.domain.lifecycle import PdlcError, TransientError
from pdlc.domain.model import (
    evidence_comment_text,
    find_marked_comments,
    item_gate,
    item_status,
    read_section,
    remove_section,
    timeline_formatted_at,
)
from pdlc.internal.inputs import load_json_array, print_help, require_file, resolve_text, wants_help
from pdlc.internal.vcs import diff_stat, diff_text, head_commit, touched_files, uncommitted_changes
from pdlc.internal.invalidation import record_patch_plan
from pdlc.internal.pull_requests import record_open_review_comments, record_pull_requests
from pdlc.internal.stack import task_branch_name
from pdlc.internal.review_stamp import clear_stamp, findings_path, restore_reviewed, write_stamp
from pdlc.internal.scratch import replace_cache_file, scratch_path, write_scratch
from pdlc.internal.workitem import (
    comments_for_issue,
    item_branch_slug,
    pipeline_for_item,
    record_snapshot,
    resolve_item,
    tasks_by_number,
    task_tree,
)
from pdlc.commands.inspect_verify import _readiness as _verify_readiness
from pdlc.commands.inspect_verify import _stale_rows as _verify_stale_rows
from pdlc.internal.verification import ledger, reports as verify_reports, reusable, skeleton, ui_journeys
from pdlc.prompts.assemble import render
from pdlc.prompts.context import (
    FR_C_PATTERN,
    UJ_PATTERN,
    covered_text,
    dependency_summaries,
    plan_body,
    task_headline,
    task_tag,
)

# The unit this brief describes must be the unit the Implementation loop is on,
# so the routing is imported from `pdlc inspect implement` rather than restated:
# a second copy would drift and brief an agent on work the loop is not doing.
from pdlc.commands.inspect_implement import (
    _TRIAGE_SOURCES,
    _eligible,
    _fixes,
    _latest_invalidation,
    _readiness,
    _stack_order,
)
from pdlc.internal.attachments import attachments_for_item, attachments_list
from pdlc.internal.failure import report_failure

TECH_PLAN_STAGE = "Technical Plan"
TASKS_STAGE = "Tasks"
UI_STAGE = "UI"
IMPLEMENTATION_STAGE = "Implementation"

# A brief with nothing for its agent to do: the caller skips that dispatch and
# carries on, unlike a refusal (exit 1), which stops it.
EXIT_NOTHING_TO_BRIEF = 3


class NothingToBrief(PdlcError):
    """The findings hand this agent nothing to do, so no brief is written."""


BRIEF_COMMANDS = (
    "task-implementer", "task-reviewer", "task-test-writer", "acceptance-test-writer", "task-planner",
    "tech-planner", "product-reviewer", "ui-planner", "tasks-reviewer", "plan-reviewer", "cumulative-reviewer",
    "ui-journey-reviewer",
)


def _parent_body(item: dict) -> str:
    return item.get("issueBody") or ""


def _owner_repo(repository: str = "") -> tuple[str, str]:
    """`(owner, name)` of `repository` (a `PullRef`'s), else of the configured
    code repository."""
    repository = repository or get_config().code_repository or ""
    owner, _, name = repository.partition("/")
    if not owner or not name:
        raise PdlcError(
            "this brief names the pull request's repository, which is not configured; "
            "set [code.github] repository"
        )
    return owner, name


def _task_context(task: dict) -> dict[str, object]:
    """The task identity every implementer brief opens with."""
    return {
        "TASK_TAG": task_tag(task),
        "TASK_TITLE": task_headline(task),
        "TASK_BODY": (task.get("body") or "").strip(),
        "TECHNICAL_PLAN": plan_body(task),
    }


def _upstream(delivery: list[dict], chosen: dict) -> list[dict]:
    """Implemented tasks below this one in the stack — what it builds on."""
    order = _stack_order(chosen)
    return [
        task for task in sorted(delivery, key=_stack_order)
        if _stack_order(task) < order and task.get("prs")
    ]


def _requests_text(requests: list[ChangeRequest]) -> str:
    blocks: list[str] = []
    for request in requests:
        comment = request.comment
        when = timeline_formatted_at(comment["createdAt"]) if comment.get("createdAt") else "undated"
        url = f" ({comment['url']})" if comment.get("url") else ""
        blocks.append(f"### Change request — {when}{url}\n\n{evidence_comment_text(comment).strip()}")
    return "\n\n".join(blocks)


def _upstream_text(item: dict, comments: list[dict], stage: str) -> str:
    """Every upstream patch or invalidation since `stage` last published, one
    block each, or an empty string when there is none."""
    blocks: list[str] = []
    for comment in upstream_changes(comments, pipeline_for_item(item), stage):
        when = timeline_formatted_at(comment["createdAt"]) if comment.get("createdAt") else "undated"
        url = f" ({comment['url']})" if comment.get("url") else ""
        kind = "Patch" if comment["marker"] == "PATCHED" else "Invalidation"
        blocks.append(f"### {kind} — {when}{url}\n\n{evidence_comment_text(comment).strip()}")
    return "\n\n".join(blocks)


def _decisions_text(requests: list[ChangeRequest]) -> str:
    resolutions = [request for request in requests if request.source == "resolution"]
    if not resolutions:
        return "No previously recorded decisions."
    return "\n\n".join(evidence_comment_text(request.comment).strip() for request in resolutions)


def _checks_text(red: list[dict]) -> str:
    return "\n".join(f"- PR {pull_request_label(pr)}: {pr.get('checks')} ({pr['url']})" for pr in red)


def _implement_context(
    item: dict, delivery: list[dict], chosen: dict, comments: list[dict], findings: str,
) -> dict[str, object]:
    body = _parent_body(item)
    task_body = chosen.get("body") or ""
    if not findings and chosen.get("implementationInvalidated"):
        invalidation = _latest_invalidation(chosen, comments)
        findings = evidence_comment_text(invalidation).strip() if invalidation else ""
    return {
        "EXECUTION_SCOPE": "this one task",
        **_task_context(chosen),
        "PARENT_WORK_ITEM": str(item["content"]["number"]),
        "REQUIREMENTS_TEXT": covered_text(body, "Product", task_body, FR_C_PATTERN),
        "DEPENDENCY_SUMMARIES": dependency_summaries(_upstream(delivery, chosen)),
        "JOURNEY_TEXT": covered_text(body, "UI", task_body, UJ_PATTERN),
        "FINDINGS": findings,
        "FINDINGS_TEXT": findings,
        "UPSTREAM_CHANGES": _upstream_text(item, comments, "Implementation"),
        "BUILD_RUN_SKILL": get_capabilities().skill("build-run") or "",
        # Mockups and screenshots inform the UI; a CORE task goes without them.
        "ATTACHMENTS": attachments_list(attachments_for_item(item)) if chosen.get("isUI") else "",
    }


def _pr_fix_context(
    item: dict, task: dict, pr: PullRef, red: list[dict], requests: list[ChangeRequest],
) -> dict[str, object]:
    owner, name = _owner_repo(pr.repository)
    checks = _checks_text(red)
    return {
        "EXECUTION_SCOPE": "this one pull request",
        **_task_context(task),
        "PARENT_WORK_ITEM": str(item["content"]["number"]),
        "PR_NUMBER": str(pr.number),
        "OWNER": owner,
        "REPO": name,
        "DECISIONS_TEXT": _decisions_text(requests),
        "FAILING_CHECKS": checks,
        "FAILING_CHECKS_TEXT": checks,
    }


def _triage_context(item: dict, delivery: list[dict], requests: list[ChangeRequest]) -> dict[str, object]:
    slug = item_branch_slug(item)
    implemented = sorted((task for task in delivery if task.get("prs")), key=_stack_order)
    return {
        "EXECUTION_SCOPE": "this one set of requests",
        "OPEN_REQUESTS_TEXT": _requests_text(requests),
        "STACK": [
            {
                "BRANCH": task_branch_name(slug, task["taskId"]),
                **_task_context(task),
            }
            for task in implemented
        ],
    }


@dataclass(frozen=True)
class _Unit:
    """The one unit of work every brief for this pass describes."""

    item: dict
    delivery: list[dict]
    comments: list[dict]
    task: dict  # the task under review/test; the top task for a triage unit
    kind: str  # implement | pr-fix | triage
    pr: PullRef | None = None
    red: tuple[dict, ...] = ()
    requests: tuple[ChangeRequest, ...] = ()


def _resolve(issue: str) -> _Unit:
    """The unit the Implementation loop is on, or a refusal naming what is due."""
    item, tasks, comments = record_snapshot(issue)
    delivery = [task for task in tasks if task.get("taskId")]
    ready, message = _readiness(item, delivery)
    if not ready:
        raise PdlcError(message)

    eligible = sorted((task for task in delivery if _eligible(task)), key=_stack_order)
    if item_gate(item) in ("Pending", "Stale") and eligible:
        return _Unit(item, delivery, comments, eligible[0], "implement")

    pull_requests = record_pull_requests(issue, record=item, tasks=delivery)
    threads = record_open_review_comments(issue, record=item, tasks=delivery)
    fixes = _fixes(delivery, pull_requests, threads)
    requests = tuple(
        request
        for request in open_change_requests(comments, pipeline_for_item(item), "Implementation").requests
        if request.source in _TRIAGE_SOURCES
    )

    if fixes:
        fix = fixes[0]
        # Red checks with no thread to judge are ordinary rework: the causes are
        # the findings, and the implementation brief is the one that carries them.
        kind = "pr-fix" if fix.threads else "implement"
        return _Unit(item, delivery, comments, fix.task, kind, fix.pr, tuple(fix.red), requests)
    if requests:
        implemented = sorted((task for task in delivery if task.get("prs")), key=_stack_order)
        if not implemented:
            raise PdlcError("change requests are open but no delivery task has a registered pull request")
        return _Unit(item, delivery, comments, implemented[-1], "triage", requests=requests)

    raise PdlcError(
        "no unit is due for a sub-agent: every delivery task is implemented and nothing is open to fix or triage"
    )


def _implementer_brief(unit: _Unit, review: str = "") -> str:
    """The brief for the unit's form; `review` is the reviewer's implementation
    findings, carried by whichever form is due. Every form also lists the
    working tree's uncommitted changes, earlier work an interrupted run left."""
    extra = {"REVIEW_FINDINGS": review, "UNCOMMITTED_CHANGES": uncommitted_changes()}
    if unit.kind == "triage":
        return render("triage", {**_triage_context(unit.item, unit.delivery, list(unit.requests)), **extra})
    if unit.kind == "pr-fix":
        if unit.pr is None:
            raise PdlcError("a pull-request fix unit names no pull request")
        context = _pr_fix_context(unit.item, unit.task, unit.pr, list(unit.red), list(unit.requests))
        return render("pr-fix", {**context, **extra})
    findings = "\n\n".join(part for part in (_checks_text(list(unit.red)) if unit.red else "", review) if part)
    context = _implement_context(unit.item, unit.delivery, unit.task, unit.comments, findings)
    return render("implement", {**context, "UNCOMMITTED_CHANGES": extra["UNCOMMITTED_CHANGES"]})


def _review_brief(unit: _Unit, commits: str, findings_file: str) -> str:
    return render(
        "review",
        {
            "EXECUTION_SCOPE": "this one review",
            **_task_context(unit.task),
            "DIFF_STAT": diff_stat(commits),
            "DIFF": diff_text(commits),
            "DEPENDENCY_SUMMARIES": dependency_summaries(_upstream(unit.delivery, unit.task)),
            "FINDINGS_PATH": findings_file,
        },
    )


def _test_brief(
    unit: _Unit, commits: str, changed: str, traceability: str, findings: ImplementFindings | None,
    changed_code: bool = True,
) -> str:
    """`changed_code` is False when the implementing agent did not run on this
    pass, so no implementation finding was fixed and none is carried."""
    files = touched_files(commits)
    return render(
        "test",
        {
            "EXECUTION_SCOPE": "this one task",
            **_task_context(unit.task),
            **_capability_lines(),
            "TRACEABILITY_MAP": traceability,
            "IN_SCOPE_SOURCE": "\n".join(f"- {name}" for name in files) or "none",
            "WHAT_CHANGED": changed,
            "TASK_NUMBER": str(unit.task["number"]),
            "PARENT_WORK_ITEM": str(unit.item["content"]["number"]),
            "TEST_FINDINGS": findings.test if findings else "",
            "IMPLEMENTATION_FINDINGS": findings.implementation if findings and changed_code else "",
        },
    )


def _implement_findings(value: str) -> ImplementFindings:
    """The task reviewer's findings file `value` names, parsed by owner."""
    return parse_implement_findings(resolve_text(value, label="--findings"), f"--findings {value}")


def implementer_brief(work_item: str, findings: str | None = None) -> str:
    """The brief for the sub-agent writing this pass's code; with `findings`, the
    brief for fixing the reviewer's implementation findings, or `NothingToBrief`
    when the review has no blocking one."""
    review = ""
    if findings:
        parsed = _implement_findings(findings)
        if not parsed.implementation_blocking:
            raise NothingToBrief(
                f"No implementation findings in {findings}: the implementation agent is not needed and no "
                "brief was written. Continue with the skill's next step."
            )
        review = parsed.implementation
    return _implementer_brief(_resolve(work_item), review)


def reviewer_brief(work_item: str, commits: str) -> str:
    """The brief for the reviewer reading `commits` against this pass's task,
    with a fresh findings file for it to fill."""
    unit = _resolve(work_item)
    outline = render("templates/implement-review-findings", {"TASK_TAG": task_tag(unit.task)})
    path = replace_cache_file(findings_path(work_item, IMPLEMENTATION_STAGE), outline)
    return _review_brief(unit, commits, str(path))


_NO_CODE_CHANGE = "No production code changed on this pass."


def test_writer_brief(
    work_item: str, commits: str, report: str | None, traceability: str, findings: str | None,
) -> str:
    """The brief for the test writer covering what `commits` changed, and the
    reviewer's findings when a review sent the unit back."""
    if not report and not findings:
        raise PdlcError("--report is required unless --findings is given")
    return _test_brief(
        _resolve(work_item),
        commits,
        resolve_text(report, label="--report") if report else _NO_CODE_CHANGE,
        resolve_text(traceability, label="--traceability"),
        _implement_findings(findings) if findings else None,
        changed_code=bool(report),
    )


def _capability_lines() -> dict[str, object]:
    """The test-authoring line, and the test-framework line when one is routed."""
    return {
        "TEST_AUTHORING": capability_line("test-authoring"),
        "TEST_FRAMEWORK": capability_name("test-framework") and capability_line("test-framework"),
    }


def acceptance_test_writer_brief(work_item: str, traceability: str, findings: str | None) -> str:
    """The brief for the test writer covering the record's whole implemented scope.

    The scope and readiness are `pdlc inspect test`'s own, so the brief covers
    exactly what that command lists. Findings are the stage's open change
    requests off the record; `findings` adds what the record cannot carry, such
    as a red check's log excerpt.
    """
    item, tasks, comments = record_snapshot(work_item)
    ready, message = testing_readiness(item)
    if not ready:
        raise PdlcError(message)
    scope = testable_scope(tasks, record_pull_requests(work_item, record=item, tasks=tasks))
    if not scope:
        raise PdlcError("no task has closed with its implementation recorded yet — nothing is implemented")

    files = list(dict.fromkeys(name for _, prs in scope for _, touched in prs for name in touched))
    numbers = [pull_request_label(pr) for _, prs in scope for pr, _ in prs]
    requests = open_change_requests(comments, pipeline_for_item(item), item["Status"]).requests
    blocks = [_requests_text(list(requests))] if requests else []
    if findings:
        blocks.append(f"### Additional findings\n\n{resolve_text(findings, label='--findings').strip()}")
    return render(
        "acceptance-test",
        {
            "EXECUTION_SCOPE": "this one implemented scope",
            **_capability_lines(),
            "TRACEABILITY_MAP": resolve_text(traceability, label="--traceability").strip(),
            "IN_SCOPE_SOURCE": "\n".join(f"- {name}" for name in files) or "none",
            "IMPLEMENTED_TASKS": "\n".join(
                f"- `{task_tag(task)}` {task_headline(task)}" for task, _ in scope
            ),
            "TASK_NUMBERS": ", ".join(f"`{task['number']}`" for task, _ in scope),
            "PARENT_WORK_ITEM": str(item["content"]["number"]),
            "PULL_REQUESTS": ", ".join(f"`{number}`" for number in dict.fromkeys(numbers)) or "none registered",
            "FINDINGS": "\n\n".join(blocks),
            "UPSTREAM_CHANGES": _upstream_text(item, comments, "Testing"),
        },
    )


def product_reviewer_brief(draft: str, work_item: str | None, findings: str | None) -> str:
    """The brief for the reviewer checking a Product draft before it lands.

    Unlike the other briefs, which resolve a unit already on a record, the
    draft this describes may exist only as a local scratch file, so it takes
    the draft's path directly rather than resolving one from a work item, and
    the reviewer reads that file itself instead of receiving it inlined.
    `work_item` is the record being reconciled, when there is one; a fresh
    draft with no record yet drops that section, as a first review drops
    the prior findings.
    """
    current_record = (resolve_item(work_item).get("issueBody") or "").strip() if work_item else ""
    return render(
        "product-review",
        {
            "EXECUTION_SCOPE": "this one product draft review",
            "DRAFT_PATH": draft,
            "CURRENT_RECORD": current_record,
            "PRIOR_FINDINGS": resolve_text(findings, label="--findings").strip() if findings else "",
        },
    )


_INVALIDATED_STAGE = re.compile(r"^Invalidated stage:\s*(.+)$", re.MULTILINE)


def _stage_invalidation(comments: list[dict], stage: str) -> dict | None:
    """The record-level `PDLC-INVALIDATED` comment naming `stage`, newest first."""
    matching = [
        comment for comment in find_marked_comments(comments, "INVALIDATED")
        if (match := _INVALIDATED_STAGE.match(evidence_comment_text(comment))) and match.group(1).strip() == stage
    ]
    return max(matching, key=lambda comment: comment.get("createdAt") or "") if matching else None


def _stale_reason(item: dict, comments: list[dict], stage: str) -> str | None:
    """Why `stage` bounced back to Stale, or `None` when no reason is recorded."""
    if item_gate(item) != "Stale":
        return None
    invalidation = _stage_invalidation(comments, stage)
    if not invalidation:
        return None
    lines = evidence_comment_text(invalidation).splitlines()
    if not lines:
        return None
    reason = (
        "\n".join(lines[1:]).strip()
        if lines[0].startswith("Invalidated stage:")
        else lines[0]
    )
    return reason or None


def _task_tree_text(delivery: list[dict]) -> str:
    """One line per existing delivery task, or an empty string when none exist."""
    if not delivery:
        return ""
    return "\n".join(f"- `{task_tag(task)}` {task_headline(task)} ({task['state']})" for task in delivery)


def ui_planner_brief(
    work_item: str,
    follow_up: str | None,
    current_journeys_path: str | None = None,
) -> str:
    """The brief for the sub-agent authoring the record's UI section.

    Due only while `Status` is `UI`. `follow_up` carries the driver's verbatim
    request, read the same way `task_planner_brief` reads its own
    `--follow-up`. `current_journeys_path` names an unpublished UI fragment to
    revise, such as the draft a reviewer saw; without one, a published `## UI`
    section is copied to the work-item cache for revision.
    """
    current_journeys = (
        str(require_file("--current-journeys-path", current_journeys_path).resolve())
        if current_journeys_path is not None
        else ""
    )
    if current_journeys:
        restore_reviewed(
            work_item, UI_STAGE,
            ui_reviewer_command(work_item, current_journeys), ui_planner_command(work_item, current_journeys),
        )
    item, tasks, comments = record_snapshot(work_item)
    status = item_status(item)
    if status != "UI":
        raise PdlcError(f"no UI section is due: the record is at {status or 'an unset status'}, not UI")
    # A new planning pass begins, so the fragment last reviewed is no longer the one to land.
    clear_stamp(work_item, UI_STAGE)

    delivery = [task for task in tasks if task.get("taskId")]
    parent_body = _parent_body(item)
    published = read_section(parent_body, "UI")
    # A supplied draft and a generated copy of the published section are revised the same way.
    fragment = current_journeys or (
        str(write_scratch(scratch_path(work_item, "ui-planner-fragment"), published)) if published.strip() else ""
    )
    change_requests = _requests_text(list(open_change_requests(comments, pipeline_for_item(item), status).requests))
    return render(
        "ui-planner",
        {
            "EXECUTION_SCOPE": "this one UI section",
            "UX_DESIGN_LINE": capability_line("ux-design"),
            "PARENT_WORK_ITEM": str(item["content"]["number"]),
            # The fragment file is the only copy of the UI section the planner sees.
            "PARENT_BODY": (remove_section(parent_body, "UI") if fragment else parent_body).rstrip(),
            "GATE_STATE": item_gate(item) or "unset",
            "STALE_REASON": _stale_reason(item, comments, status),
            "UPSTREAM_CHANGES": _upstream_text(item, comments, status),
            "TASK_TREE": _task_tree_text(delivery),
            "FRAGMENT_PATH": fragment,
            "CHANGE_REQUESTS": change_requests,
            "DRIVER_FOLLOWUP": _filled_text(follow_up, "--follow-up", UI_STAGE),
            "ATTACHMENTS": attachments_list(attachments_for_item(item)),
        },
    )


def task_planner_brief(
    work_item: str,
    follow_up: str | None,
    current_tasks_manifest_path: str | None = None,
) -> str:
    """The brief for the sub-agent decomposing the record into delivery tasks.

    Due only while `Status` is `Tasks`; `follow_up` carries the driver's
    verbatim request on a re-authoring pass, read the same way `--findings`
    reaches the test-writer briefs. `current_tasks_manifest_path` names an
    unpublished manifest to revise, such as the draft a reviewer saw; without
    one, the published tasks are copied to the work-item cache for revision.
    """
    current_tasks_manifest = (
        str(require_file("--current-tasks-manifest-path", current_tasks_manifest_path).resolve())
        if current_tasks_manifest_path is not None
        else ""
    )
    if current_tasks_manifest:
        restore_reviewed(
            work_item, TASKS_STAGE,
            tasks_reviewer_command(work_item, current_tasks_manifest),
            tasks_planner_command(work_item, current_tasks_manifest),
        )
    item, tasks, comments = record_snapshot(work_item)
    status = item_status(item)
    if status != "Tasks":
        raise PdlcError(f"no task breakdown is due: the record is at {status or 'an unset status'}, not Tasks")

    delivery = [task for task in tasks if task.get("taskId")]
    change_requests = _requests_text(list(open_change_requests(comments, pipeline_for_item(item), status).requests))
    driver_followup = _filled_text(follow_up, "--follow-up", TASKS_STAGE)
    # A supplied draft and a generated copy of the published tree are revised the same way.
    manifest = current_tasks_manifest or _task_planner_manifest(work_item, delivery)
    # A new planning pass begins, so the files last reviewed are no longer the ones to land.
    clear_stamp(work_item, TASKS_STAGE)

    return render(
        "task-planner",
        {
            "EXECUTION_SCOPE": "this one breakdown",
            "PARENT_WORK_ITEM": str(item["content"]["number"]),
            "PARENT_BODY": _parent_body(item).rstrip(),
            "STALE_REASON": _stale_reason(item, comments, status),
            "UPSTREAM_CHANGES": _upstream_text(item, comments, status),
            "MANIFEST_PATH": manifest,
            "EXISTING_TASKS": [
                {
                    "TASK_ID": str(task["taskId"]),
                    "TASK_TITLE": task_headline(task),
                    "TASK_PROGRESS": ", ".join((
                        str(task.get("state", "OPEN")).lower(),
                        "planned" if task.get("hasPlan") else "unplanned",
                        "implemented" if task.get("hasImplementation") else "unimplemented",
                    )),
                }
                for task in delivery
            ],
            "CHANGE_REQUESTS": change_requests,
            "DRIVER_FOLLOWUP": driver_followup,
        },
    )


def _task_planner_manifest(work_item: str, delivery: list[dict]) -> str:
    """Give a rework pass editable copies without embedding task bodies in its brief."""
    if not delivery:
        return ""
    entries = []
    for task in delivery:
        fields = stored_fields(task)
        baseline = snapshot(fields)
        body_path = write_scratch(scratch_path(work_item, f"task-planner-{task['taskId']}"), fields.pop("body"))
        entries.append({
            "id": task["taskId"], "number": task["number"], "action": "retain", **fields,
            "body": str(body_path),
            "baseline": baseline,
        })
    manifest_path = write_scratch(
        scratch_path(work_item, "task-planner-manifest", ".json"),
        json.dumps(entries, indent=2) + "\n",
    )
    return str(manifest_path)


def _tech_plan_scope(tasks: list[dict]) -> list[dict]:
    """The tasks the Technical Plan stage plans: open and not yet implemented, lowest in the stack first."""
    return sorted(
        (task for task in tasks if task.get("taskId") and task["state"] != "CLOSED" and not task["hasImplementation"]),
        key=_stack_order,
    )


def _tech_plan_manifest(work_item: str, scope: list[dict]) -> Path:
    """Write one editable task file per task in scope, plus the manifest naming them."""
    entries = []
    for task in scope:
        body = task.get("body") or ""
        plan = stored_plan(task.get("planComment"))
        path = write_scratch(scratch_path(work_item, f"tech-planner-{task['taskId']}"), render_plan_file(body, plan))
        entries.append({
            "id": task["taskId"], "number": task["number"], "title": task_headline(task),
            "file": str(path), "baseline": plan_baseline(body, plan),
        })
    return write_scratch(
        scratch_path(work_item, "tech-planner-manifest", ".json"),
        json.dumps(entries, indent=2) + "\n",
    )


def _plan_manifest_entries(manifest_path: Path, work_item: str) -> list[dict]:
    entries = load_json_array("--manifest", manifest_path, allow_empty=False)
    errors = manifest_errors(entries)
    if errors:
        listed = "\n".join(f"  - {error}" for error in errors)
        raise PdlcError(f"{manifest_path} is not a plan manifest pdlc generated:\n{listed}\n{regenerate(work_item)}")
    return entries


_NO_PLAN, _DRAFTED, _PLANNED = "no plan yet", "drafted, not yet landed", "planned"


def _task_plan_status(entry: dict, task: dict | None) -> str:
    """Where a task's plan stands, read from its task file against its recorded plan.

    An earlier pass's drafts live only in the files until they land, so the
    record alone would call a drafted task unplanned. A file that no longer
    parses was edited by an earlier pass, so it counts as a draft to revise.
    """
    recorded = stored_plan((task or {}).get("planComment"))
    path = Path(entry["file"])
    parsed = parse_plan_file(path.read_text(encoding="utf-8"))[0] if path.is_file() else None
    if parsed is None:
        return _DRAFTED if path.is_file() else (_PLANNED if recorded else _NO_PLAN)
    if not parsed.plan:
        return _NO_PLAN
    return _PLANNED if same_plan(parsed.plan, recorded) else _DRAFTED


def tech_planner_brief(work_item: str, follow_up: str | None, current_plan_manifest_path: str | None = None) -> str:
    """The brief for the sub-agent spiking the record's open tasks into plans.

    Due only while `Status` is `Technical Plan`. Every open, unimplemented task
    gets an editable file holding its body and its existing plan, so a
    reconciling pass edits what it would overwrite in place; which of them the
    evidence sends back is the planner's call. `current_plan_manifest_path`
    names a manifest from an earlier pass to keep revising, such as the one a
    reviewer saw; a new planning pass begins either way, so any review stamp
    is cleared once the reviewed files are confirmed untouched.
    """
    item, tasks, comments = record_snapshot(work_item)
    status = item_status(item)
    if status != "Technical Plan":
        raise PdlcError(f"no technical plan is due: the record is at {status or 'an unset status'}, not Technical Plan")

    scope = _tech_plan_scope(tasks)
    if not scope:
        raise PdlcError("nothing to plan: no delivery task is open and unimplemented")

    if current_plan_manifest_path is not None:
        manifest = require_file("--current-plan-manifest-path", current_plan_manifest_path).resolve()
        restore_reviewed(
            work_item, TECH_PLAN_STAGE,
            plan_reviewer_command(work_item, manifest), plan_planner_command(work_item, manifest),
        )
    else:
        manifest = _tech_plan_manifest(work_item, scope)
    entries = _plan_manifest_entries(manifest, work_item)
    clear_stamp(work_item, TECH_PLAN_STAGE)

    upstream = _upstream_text(item, comments, status)
    change_requests = _requests_text(list(open_change_requests(comments, pipeline_for_item(item), status).requests))
    driver_followup = _filled_text(follow_up, "--follow-up", TECH_PLAN_STAGE)
    # The sections a planned task is checked against; only those that render are named.
    sources = [
        name
        for name, text in (
            ("upstream changes", upstream), ("change requests", change_requests), ("driver follow-up", driver_followup),
        )
        if text
    ]
    change_sources = " and ".join((", ".join(sources[:-1]), sources[-1]) if len(sources) > 1 else sources)
    by_id = {task["taskId"]: task for task in tasks if task.get("taskId")}
    statuses = {entry["id"]: _task_plan_status(entry, by_id.get(entry["id"])) for entry in entries}

    def listed(status: str) -> str:
        return ", ".join(task_id for task_id, value in statuses.items() if value == status)

    unplanned, drafted, planned = listed(_NO_PLAN), listed(_DRAFTED), listed(_PLANNED)
    return render(
        "tech-planner",
        {
            "EXECUTION_SCOPE": "this one planning pass",
            "PARENT_WORK_ITEM": str(item["content"]["number"]),
            "PARENT_BODY": _parent_body(item).rstrip(),
            "MANIFEST_PATH": str(manifest),
            "UNPLANNED_TASKS": unplanned,
            "DRAFTED_TASKS": drafted,
            "PLANNED_TASKS": planned,
            "PLANNED_TO_CHECK": bool(planned and change_sources),
            "PLANNED_SETTLED": bool(planned and not change_sources),
            "CHANGE_SOURCES": change_sources,
            "TASKS": [
                {
                    "TASK_ID": entry["id"],
                    "TASK_TITLE": entry["title"],
                    "TASK_STATUS": statuses[entry["id"]],
                    "TASK_FILE": entry["file"],
                }
                for entry in entries
            ],
            "UPSTREAM_CHANGES": upstream,
            "CHANGE_REQUESTS": change_requests,
            "DRIVER_FOLLOWUP": driver_followup,
        },
    )


def _stored_task(entry: dict, work_item: str) -> dict:
    """The published task a manifest `remove` entry names, read by its number."""
    number = entry.get("number")
    if not isinstance(number, int):
        raise PdlcError(f"removed task {entry.get('id') or '?'} has no task number")
    try:
        matches = tasks_by_number([str(number)])
    except TransientError:
        raise
    except PdlcError as error:
        matches, lookup = [], f": {error}"
    else:
        lookup = ""
    if len(matches) != 1:
        raise PdlcError(
            f"manifest removes {entry.get('id') or '?'} as task #{number}, which could not be read{lookup};"
            f" the manifest is out of date or was edited by hand, so run `pdlc prompt task-planner {work_item}`"
            " for a fresh manifest and re-dispatch the task planner agent with it"
        )
    return matches[0]


def _manifest_artifact_text(manifest_path: Path, work_item: str) -> str:
    """Every active manifest entry rendered with its task body in full."""
    entries = load_json_array("--manifest", manifest_path, allow_empty=False)
    blocks: list[str] = []
    for entry in entries:
        if entry.get("action") == "remove":
            stored = _stored_task(entry, work_item)
            header = f"### {entry.get('id') or '?'} — {stored['title']}"
            meta = f"remove: {entry.get('reason') or 'no reason'}"
            body = (stored.get("body") or "").strip()
        else:
            header = f"### {entry.get('id') or '(new task)'} — {entry.get('title') or 'untitled'}"
            kind = f"type: {entry.get('type')}"
            meta = f"{kind}, covers: {entry.get('covers')}, depends: {entry.get('depends')}"
            body_path = entry.get("body")
            if not body_path:
                raise PdlcError(f"manifest entry {entry.get('id') or '?'} has no body file")
            body = require_file(f"manifest entry {entry.get('id') or '?'} body", body_path).read_text(
                encoding="utf-8"
            ).strip()
        blocks.append(f"{header}\n{meta}\n\n{body}")
    return "\n\n---\n\n".join(blocks)


def _manifest_review_tasks(manifest_path: Path, work_item: str) -> tuple[list[dict], list[dict]]:
    """The manifest's entries as the reviewer's task list, plus the stored body
    of every task it removes, which has no file of its own to read."""
    entries = load_json_array("--manifest", manifest_path, allow_empty=False)
    tasks: list[dict] = []
    removed: list[dict] = []
    for entry in entries:
        task_id = entry.get("id") or "(new task)"
        if entry.get("action") == "remove":
            stored = _stored_task(entry, work_item)
            reason = entry.get("reason") or "no reason"
            tasks.append({
                "TASK_ID": task_id, "TASK_TITLE": stored["title"], "TASK_ACTION": "remove",
                "TASK_DETAIL": f"leaves scope: {reason}",
            })
            removed.append({
                "TASK_ID": task_id, "TASK_TITLE": stored["title"], "REMOVE_REASON": reason,
                "TASK_BODY": (stored.get("body") or "").strip(),
            })
            continue
        kind = entry.get("type")
        references: dict[str, list[str]] = {}
        for field in ("covers", "depends"):
            values = entry.get(field, [])
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                raise PdlcError(
                    f"manifest entry {task_id} {field} must be an array of strings; "
                    "fix the manifest and rerun the reviewer"
                )
            references[field] = values
        coverage = (
            f"{kind}, covers {', '.join(references['covers']) or 'nothing'}, "
            f"depends on {', '.join(references['depends']) or 'nothing'}"
        )
        body = require_file(f"manifest entry {task_id} body", entry.get("body")).resolve()
        detail = f"`{body}`; {coverage}"
        tasks.append({
            "TASK_ID": task_id, "TASK_TITLE": entry.get("title") or "untitled",
            # An existing task keeps its number; without an action it is retained, which may still rewrite it.
            "TASK_ACTION": entry.get("action") or ("retain" if "number" in entry else "create"),
            "TASK_DETAIL": detail,
        })
    return tasks, removed


def _manifest_body_files(manifest_path: Path) -> list[Path]:
    """The task body files a Tasks manifest names; a removal has none."""
    return [
        Path(entry["body"]).resolve()
        for entry in load_json_array("--manifest", manifest_path)
        if entry.get("action") != "remove" and isinstance(entry.get("body"), str)
    ]


def _findings_outline(review: str) -> str:
    return render("templates/review-findings", {"REVIEW": review})


def _findings_file(work_item: str, review: str) -> str:
    """A fresh findings outline for one review, at a fixed path per review.

    Written after the brief has read its own `--findings`, which may be this
    same file from the previous pass.
    """
    return str(replace_cache_file(findings_path(work_item, review), _findings_outline(review)))


def _filled_text(value: str | None, label: str, review: str) -> str:
    """The text `value` names, or "" when there is none.

    A findings file still holding the unfilled outline carries no findings,
    e.g. when a reviewer brief is re-run and has already reset its own file,
    or a reviewer replied without writing its findings.
    """
    text = resolve_text(value, label=label).strip() if value else ""
    return "" if text == _findings_outline(review).strip() else text


def _restore_or_restart(work_item: str, stage: str, status: str | None, rereview: str, replan: str) -> None:
    """Protect the files handed to the stage's last review before a new one.

    At the stage itself, an edit since that review is undone and refused, since
    only a planning brief starts a new pass. From a later stage the review is of
    a patch, whose author revises the draft itself, so its revision starts the
    new pass here instead.
    """
    if status == stage:
        restore_reviewed(work_item, stage, rereview, replan)
    else:
        clear_stamp(work_item, stage)


def _published_review_files(work_item: str) -> tuple[str | None, str | None]:
    """Fresh files holding the published UI section or task breakdown, whichever
    the record's status names, as (manifest, fragment)."""
    item, tasks, _ = record_snapshot(work_item)
    status = item_status(item)
    if status == UI_STAGE:
        published = read_section(_parent_body(item), "UI")
        if not published.strip():
            raise PdlcError("no UI section is published to review; pass --fragment FILE")
        return None, str(write_scratch(scratch_path(work_item, "tasks-review-fragment"), published))
    if status == TASKS_STAGE:
        manifest = _task_planner_manifest(work_item, [task for task in tasks if task.get("taskId")])
        if not manifest:
            raise PdlcError("no delivery tasks are published to review; pass --manifest FILE")
        return manifest, None
    raise PdlcError(f"no UI section or task breakdown is due: the record is at {status or 'an unset status'}; pass --manifest or --fragment")


def tasks_reviewer_brief(
    work_item: str, manifest: str | None, fragment: str | None, findings: str | None,
) -> str:
    """The brief for the reviewer checking a UI fragment or Tasks breakdown
    before it lands. Pass at most one of `manifest` (the Tasks breakdown) or
    `fragment` (the UI section's content) — the two artifacts this reviewer
    checks, never both in the same pass. With neither, the artifact the record's
    status names is written to fresh files as published, for review as it
    stands. The reviewer reads the artifact from its files rather than a copy
    inlined in the brief. The fragment must be a file, since the stage lands
    that same file.
    """
    if manifest and fragment:
        raise PdlcError("pass at most one of --manifest or --fragment")
    if not manifest and not fragment:
        manifest, fragment = _published_review_files(work_item)
    manifest_path = str(require_file("--manifest", manifest).resolve()) if manifest else ""
    item = resolve_item(work_item)
    status = item_status(item)
    if manifest_path:
        _restore_or_restart(
            work_item, TASKS_STAGE, status,
            tasks_reviewer_command(work_item, manifest_path), tasks_planner_command(work_item, manifest_path),
        )
    parent_body = _parent_body(item)
    tasks, removed = _manifest_review_tasks(Path(manifest_path), work_item) if manifest else ([], [])
    if manifest_path:
        write_stamp(work_item, TASKS_STAGE, [Path(manifest_path), *_manifest_body_files(Path(manifest_path))])
    fragment_path = ""
    if fragment:
        if fragment.startswith("text:") or fragment == "-":
            raise PdlcError("--fragment takes the UI fragment's FILE, the same file `pdlc post tasks --stage UI --body` lands")
        fragment_path = str(require_file("--fragment", fragment).resolve())
        _restore_or_restart(
            work_item, UI_STAGE, status,
            ui_reviewer_command(work_item, fragment_path), ui_planner_command(work_item, fragment_path),
        )
        write_stamp(work_item, UI_STAGE, [Path(fragment_path)])
    review = UI_STAGE if fragment_path else TASKS_STAGE
    prior_findings = _filled_text(findings, "--findings", review)
    outline_path = _findings_file(work_item, review)
    return render(
        "tasks-review",
        {
            "EXECUTION_SCOPE": "this one artifact review",
            "PARENT_WORK_ITEM": str(item["content"]["number"]),
            # A fragment replaces the published UI section, so only the fragment's copy is under review.
            "PARENT_BODY": (remove_section(parent_body, "UI") if fragment_path else parent_body).rstrip(),
            "FRAGMENT_PATH": fragment_path,
            "MANIFEST_PATH": manifest_path,
            "TASKS": tasks,
            "REMOVED_TASKS": removed,
            # Empty on a first review, which drops the section from the brief.
            "PRIOR_FINDINGS": prior_findings,
            "FINDINGS_PATH": outline_path,
        },
    )


def plan_reviewer_brief(work_item: str, manifest: str | None, findings: str | None) -> str:
    """The brief for the reviewer checking a pass's delivery-task plans before
    they land. `manifest` is the plan manifest `pdlc prompt tech-planner`
    generated; without one, the recorded plans are written to fresh task files
    for review as they stand. The reviewer reads each task file rather than a
    copy inlined here. A plan that replaces a recorded one carries the recorded
    plan too, since the file no longer shows it. The files handed over are
    recorded, so the stage lands only what was reviewed.
    """
    if manifest is not None:
        manifest_path = require_file("--manifest", manifest).resolve()
        restore_reviewed(
            work_item, TECH_PLAN_STAGE,
            plan_reviewer_command(work_item, manifest_path), plan_planner_command(work_item, manifest_path),
        )
    item, tasks, _ = record_snapshot(work_item)
    if manifest is None:
        status = item_status(item)
        if status != "Technical Plan":
            raise PdlcError(f"no technical plan to review: the record is at {status or 'an unset status'}, not Technical Plan")
        scope = _tech_plan_scope(tasks)
        if not scope:
            raise PdlcError("nothing to review: no delivery task is open and unimplemented")
        manifest_path = _tech_plan_manifest(work_item, scope).resolve()
    by_id = {task["taskId"]: task for task in tasks if task.get("taskId")}
    entries = _plan_manifest_entries(manifest_path, work_item)
    listed: list[dict] = []
    replaced: list[dict] = []
    for entry in entries:
        task = by_id.get(entry["id"])
        if task is None:
            raise PdlcError(f"--manifest names {entry['id']!r}, which is not a delivery task on this record")
        path = require_file(f"manifest entry {entry['id']} file", entry["file"]).resolve()
        planned, errors = parse_plan_file(path.read_text(encoding="utf-8"))
        if planned is None:
            raise PdlcError(
                f"{entry['id']} file {path}: {'; '.join(errors)}; run `pdlc post plan --work-item {work_item}"
                f" --manifest {manifest_path} --dry-run` and send its failures back to the planner before review"
            )
        recorded = stored_plan(task.get("planComment"))
        if not recorded:
            change = "new plan"
        elif same_plan(planned.plan, recorded):
            change = "recorded plan, unchanged"
        else:
            change = "replaces its recorded plan"
            replaced.append({"TASK_ID": entry["id"], "TASK_TITLE": entry["title"], "RECORDED_PLAN": recorded})
        listed.append({"TASK_ID": entry["id"], "TASK_TITLE": entry["title"], "TASK_CHANGE": change, "TASK_FILE": str(path)})
    write_stamp(work_item, TECH_PLAN_STAGE, [manifest_path, *(Path(entry["TASK_FILE"]) for entry in listed)])
    prior_findings = _filled_text(findings, "--findings", TECH_PLAN_STAGE)
    return render(
        "plan-review",
        {
            "EXECUTION_SCOPE": "this one planning review",
            "PARENT_WORK_ITEM": str(item["content"]["number"]),
            "PARENT_BODY": _parent_body(item).rstrip(),
            "MANIFEST_PATH": str(manifest_path),
            "TASKS": listed,
            "REPLACED_PLANS": replaced,
            # Empty on a first review, which drops the section from the brief.
            "PRIOR_FINDINGS": prior_findings,
            "FINDINGS_PATH": _findings_file(work_item, TECH_PLAN_STAGE),
        },
    )


def patch_reviewer_brief(work_item: str, stage: str, body: str | None, manifest: str | None) -> str:
    """The brief for PDLC's own patch reviewer, which judges whether a reviewed
    correction to `stage`'s landed artifact affects any stage between it and
    the active one. The draft is the same input that stage's landing command
    takes: `body` for Product and UI, `manifest` for Tasks. Refused when the
    record may not patch `stage`, or when no stage lies in between, since no
    impact report is needed then.
    """
    if stage == "Tasks" and (not manifest or body):
        raise PdlcError("--stage Tasks takes --manifest FILE")
    if stage != "Tasks" and (not body or manifest):
        raise PdlcError(f"--stage {stage} takes --body FILE")
    item, tasks, _ = record_snapshot(work_item)
    plan = record_patch_plan(item, stage, None, dry_run=True)
    if not plan.impact_required:
        raise PdlcError(
            f"no stage lies between {stage} and {plan.source.stage}; the patch needs no impact report"
        )
    draft = (
        _manifest_artifact_text(require_file("--manifest", manifest), work_item) if manifest
        else require_file("--body", body).read_text(encoding="utf-8").strip()
    )
    delivery = [task for task in tasks if task.get("taskId")]
    task_bodies = "\n\n---\n\n".join(
        f"### {task_tag(task)} — {task_headline(task)}\n\n{(task.get('body') or '').strip()}" for task in delivery
    )
    return render(
        "patch-review",
        {
            "EXECUTION_SCOPE": "this one patch impact review",
            "PARENT_WORK_ITEM": str(item["content"]["number"]),
            "PATCHED_STAGE": stage,
            "ACTIVE_STAGE": plan.source.stage,
            "INTERMEDIATE_STAGES": ", ".join(plan.intermediate),
            "PARENT_BODY": _parent_body(item).rstrip(),
            "TASK_BODIES": task_bodies or "none",
            "DRAFT": draft,
        },
    )


def cumulative_reviewer_brief(shipped: str, unchanged: str, constraints: str, scope: str | None) -> str:
    """The brief for the general-purpose sub-agent running the project's
    cumulative-review capability over a record's whole change scope.

    The sub-agent knows nothing about PDLC, so every field is plain language,
    never an `FR-*`/`C-*` identifier or a work-item number; translating those
    is this brief's caller's job, which is why they arrive as flags rather
    than being resolved from a record here. `scope` defaults to the branch
    diff, the common case for work still unmerged on its own branch.
    """
    return render(
        "cumulative-review",
        {
            "EXECUTION_SCOPE": "this one review",
            "CUMULATIVE_REVIEW_LINE": capability_line("cumulative-review"),
            "SCOPE": (
                resolve_text(scope, label="--scope").strip() if scope
                else "The current branch's diff against its base branch"
            ),
            "SHIPPED_BEHAVIOR": resolve_text(shipped, label="--shipped").strip(),
            "UNCHANGED_BEHAVIOR": resolve_text(unchanged, label="--unchanged").strip(),
            "CONSTRAINTS": resolve_text(constraints, label="--constraints").strip(),
        },
    )


def _verify_journeys(work_item: str) -> tuple[list[str], bool]:
    """Every `UJ-*` journey still needing a fresh pass, full text, and whether
    UX needs one too — the same carried-forward resolution `pdlc inspect
    verify` renders as its own `## Journeys to review` section, read here
    directly rather than re-derived.
    """
    item = resolve_item(work_item)
    ready, message = _verify_readiness(item, lambda: _verify_stale_rows(work_item))
    if not ready:
        raise PdlcError(message)

    tasks = task_tree(work_item)
    body = item.get("issueBody") or ""
    comments = comments_for_issue(work_item)
    open_comments = record_open_review_comments(work_item, record=item, tasks=tasks)
    all_reports, _ = verify_reports(work_item, comments)
    known = ledger(all_reports)
    report = skeleton(work_item, head_commit(), tasks, body, open_comments, known, reusable(all_reports, tasks))

    if report["journeys"] is None:
        raise PdlcError("no UI tasks on this record — the user-journey reviewer has nothing to check")

    blocks = ui_journeys(body)
    to_review = [blocks[row["journey"]] for row in report["journeys"] if row["result"] is None]
    ux_stale = report["ux"]["result"] is None
    if not to_review and not ux_stale:
        raise PdlcError("every journey and UX are already carried forward — nothing is due for a fresh pass")
    return to_review, ux_stale


def ui_journey_reviewer_brief(work_item: str, description: str) -> str:
    """The brief for the sub-agent walking a record's UI journeys, read-only.

    `description` is the calling skill's one-sentence account of what
    shipped, since the sub-agent knows nothing about PDLC and cannot resolve
    it from the record itself. Refuses when the record carries no UI task, or
    when every journey and UX are already carried forward from an earlier
    pass — the same case `pdlc inspect verify` reports as nothing left to
    dispatch.
    """
    to_review, ux_stale = _verify_journeys(work_item)
    return render(
        "ui-journey-review",
        {
            "EXECUTION_SCOPE": "this one verification pass",
            "BUILD_RUN_LINE": capability_line("build-run"),
            "DESCRIPTION": resolve_text(description, label="--description").strip(),
            "HAS_JOURNEYS": bool(to_review),
            "JOURNEYS": [{"TEXT": block} for block in to_review],
            "UX_STALE": ux_stale,
        },
    )


def add_common_arguments(parser: argparse.ArgumentParser, command: str) -> None:
    """The work item and `--inline`, which every brief command takes alike."""
    parser.add_argument("work_item")
    add_inline_argument(parser)


def add_inline_argument(parser: argparse.ArgumentParser) -> None:
    """`--inline` prints the brief itself; a convenience for humans, kept out of help."""
    parser.add_argument("--inline", action="store_true", help=argparse.SUPPRESS)


def emit(brief: str, work_item: str, command: str, inline: bool) -> None:
    """Print the path of the scratch file now holding the brief, or the brief itself.

    The command name is part of that path so one pass's three briefs cannot
    overwrite each other: a caller that still held the implementer's path would
    otherwise read the reviewer's brief back out of it.
    """
    if inline:
        sys.stdout.write(brief)
    else:
        print(write_scratch(scratch_path(work_item, f"prompt-{command}-{work_item}"), brief))


def run(command: str, args: argparse.Namespace, build: Callable[[], str]) -> int:
    """Render one brief, reporting a refusal without writing or printing it."""
    try:
        brief = build()
        emit(brief, args.work_item, command, args.inline)
    except NothingToBrief as nothing:
        print(nothing)
        return EXIT_NOTHING_TO_BRIEF
    except PdlcError as error:
        return report_failure(error)
    return 0


def main(argv: list[str] | None = None) -> int:
    """`pdlc prompt` alone is the index; every brief is one of its commands."""
    command_args = list(sys.argv[1:] if argv is None else argv)
    if not command_args or wants_help(command_args):
        print_help(__doc__)
        return 0
    print(
        f"pdlc: `pdlc prompt` takes one of: {', '.join(BRIEF_COMMANDS)}\n\n"
        + (__doc__ or "").strip(),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
