#!/usr/bin/env python3
"""NAME
    pdlc prompt - read-only: print the ready-to-send brief for a work item's next unit

USAGE
    - if --agent implementer:
        pdlc prompt WORK_ITEM --agent implementer [--file]
    - if --agent reviewer:
        pdlc prompt WORK_ITEM --agent reviewer --commits REVISIONS [--file]
    - if --agent test-writer:
        pdlc prompt WORK_ITEM --agent test-writer --commits REVISIONS
            --report FILE|text:BODY --traceability FILE|text:BODY
            [--findings FILE|text:BODY] [--file]

DESCRIPTION
    Prints one complete sub-agent brief for the unit of work a record has next,
    with every value already filled in. The output is sent to the sub-agent
    verbatim: it carries the task, its plan, the covered requirements, and the
    boundaries the agent works inside, and it names no PDLC command, stage, or
    gate.

    Every agent's brief describes the same unit, so the implementer, the
    reviewer, and the test writer are held to one task, one plan, and one set
    of acceptance criteria on a given pass. `implementer` needs nothing but the
    record. `reviewer` and `test-writer` read a change that exists only in the
    working tree, so they take the revisions to read; `test-writer` also takes
    the two artifacts no record carries — what the implementing agent reported
    it did, and the traceability map the coverage is written against.

    The implementer's brief is chosen from the same unit the Implementation
    loop is on, so it always matches the work that is actually due:

    - a task to implement, or one whose implementation was invalidated, gets the
      implementation brief, with the invalidation carried as findings to address;
    - a task whose pull request has unresolved review threads gets the
      review-comment brief, carrying the driver's answers to anything escalated
      earlier, and the red checks on that pull request when it has them;
    - a task whose pull request is only failing its checks gets the
      implementation brief, with those checks as the findings to address;
    - open change requests against the stage get the triage brief, carrying every
      request and the whole task stack with each branch and plan.

    Nothing due prints what the record is waiting on and exits non-zero, so a
    caller never dispatches an agent against an empty unit. The command reads the
    record and its live pull-request state; it changes nothing.

    A value the record does not carry is reported in place rather than omitted —
    a cited requirement missing from the record's `## Product` renders as "not
    found" inside the brief instead of leaving the agent a hole it cannot see.

FLAGS
    --agent AGENT           which seam's brief to build: `implementer`,
                            `reviewer`, or `test-writer`. The implementer to
                            send it to is the one `pdlc inspect task` names
                            under `## Agent`; the other two are the project's
                            configured reviewer and test-writer agents
    --commits REVISIONS     the revision or range the brief reads, as `git show`
                            accepts it; required for reviewer and test-writer
    --report FILE|text:BODY the implementing agent's report-back, carried into
                            the test brief's `## What changed`; test-writer only
    --traceability FILE|text:BODY  the traceability map the coverage is written
                            against; test-writer only
    --findings FILE|text:BODY  reviewer findings accepted as non-blocking;
                            test-writer only, and "none" when omitted
    --file                  write the brief to
                            {TEMPDIR}/{repo}-prompt-{work item}.md and print that
                            path, instead of stdout

EXAMPLES
    pdlc prompt 236 --agent implementer
    pdlc prompt 236 --agent reviewer --commits HEAD~2..HEAD
    pdlc prompt 236 --agent test-writer --commits HEAD~2..HEAD \\
        --report /tmp/impl-report.md --traceability /tmp/trace.md
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from pdlc.commands.inspect_capability import _name as capability_name
from pdlc.commands.inspect_capability import _one as capability_line
from pdlc.config import get_capabilities, get_config
from pdlc.domain.changes import ChangeRequest, open_change_requests
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import evidence_comment_text, item_gate, timeline_formatted_at
from pdlc.internal.inputs import print_help, resolve_text, wants_help
from pdlc.internal.vcs import diff_stat, diff_text, touched_files
from pdlc.internal.pull_requests import record_open_review_comments, record_pull_requests
from pdlc.internal.stack import task_branch_name
from pdlc.internal.scratch import scratch_path, write_scratch
from pdlc.internal.workitem import item_slug, pipeline_for_item, record_snapshot
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

AGENTS = ("implementer", "reviewer", "test-writer")


def _parent_body(item: dict) -> str:
    return item.get("issueBody") or ""


def _owner_repo() -> tuple[str, str]:
    repository = get_config().repository or ""
    owner, _, name = repository.partition("/")
    if not owner or not name:
        raise PdlcError(
            "this brief names the pull request's repository, which is not configured; "
            "set [backend.github] repository or pass --repo OWNER/REPO"
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


def _decisions_text(requests: list[ChangeRequest]) -> str:
    resolutions = [request for request in requests if request.source == "resolution"]
    if not resolutions:
        return "No previously recorded decisions."
    return "\n\n".join(evidence_comment_text(request.comment).strip() for request in resolutions)


def _checks_text(red: list[dict]) -> str:
    return "\n".join(f"- PR #{pr['number']}: {pr.get('checks')} ({pr['url']})" for pr in red)


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
        "BUILD_RUN_SKILL": get_capabilities().skill("build-run") or "",
    }


def _pr_fix_context(task: dict, pr: int, red: list[dict], requests: list[ChangeRequest]) -> dict[str, object]:
    owner, name = _owner_repo()
    checks = _checks_text(red)
    return {
        "EXECUTION_SCOPE": "this one pull request",
        **_task_context(task),
        "PR_NUMBER": str(pr),
        "OWNER": owner,
        "REPO": name,
        "DECISIONS_TEXT": _decisions_text(requests),
        "FAILING_CHECKS": checks,
        "FAILING_CHECKS_TEXT": checks,
    }


def _triage_context(item: dict, delivery: list[dict], requests: list[ChangeRequest]) -> dict[str, object]:
    slug = item_slug(item)
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
    pr: int | None = None
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


def _implementer_brief(unit: _Unit) -> str:
    if unit.kind == "triage":
        return render("triage", _triage_context(unit.item, unit.delivery, list(unit.requests)))
    if unit.kind == "pr-fix":
        return render(
            "pr-fix",
            _pr_fix_context(unit.task, unit.pr or 0, list(unit.red), list(unit.requests)),
        )
    findings = _checks_text(list(unit.red)) if unit.red else ""
    return render(
        "implement",
        _implement_context(unit.item, unit.delivery, unit.task, unit.comments, findings),
    )


def _review_brief(unit: _Unit, commits: str) -> str:
    return render(
        "review",
        {
            "EXECUTION_SCOPE": "this one review",
            **_task_context(unit.task),
            "DIFF_STAT": diff_stat(commits),
            "DIFF": diff_text(commits),
            "DEPENDENCY_SUMMARIES": dependency_summaries(_upstream(unit.delivery, unit.task)),
        },
    )


def _test_brief(unit: _Unit, commits: str, changed: str, traceability: str, findings: str) -> str:
    files = touched_files(commits)
    return render(
        "test",
        {
            "EXECUTION_SCOPE": "this one task",
            **_task_context(unit.task),
            "TEST_AUTHORING": capability_line("test-authoring"),
            "TEST_FRAMEWORK": capability_name("test-framework") and capability_line("test-framework"),
            "TRACEABILITY_MAP": traceability,
            "IN_SCOPE_SOURCE": "\n".join(f"- {name}" for name in files) or "none",
            "WHAT_CHANGED": changed,
            "TASK_NUMBER": str(unit.task["number"]),
            "PARENT_WORK_ITEM": str(unit.item["content"]["number"]),
            "NONBLOCKING_FINDINGS": findings or "none",
        },
    )


def build(issue: str, agent: str, args: argparse.Namespace) -> str:
    """Resolve the record's next unit and render that agent's brief in full."""
    if agent not in AGENTS:
        raise PdlcError(f"unknown agent {agent!r}; this command builds briefs for: {', '.join(AGENTS)}")
    unit = _resolve(issue)
    if agent == "implementer":
        return _implementer_brief(unit)
    if agent == "reviewer":
        return _review_brief(unit, _require(args.commits, "--commits"))
    return _test_brief(
        unit,
        _require(args.commits, "--commits"),
        resolve_text(_require(args.report, "--report"), label="--report"),
        resolve_text(_require(args.traceability, "--traceability"), label="--traceability"),
        resolve_text(args.findings, label="--findings") if args.findings else "",
    )


def _require(value: str | None, flag: str) -> str:
    if not value:
        raise PdlcError(f"{flag} is required for this agent; see `pdlc prompt --help`")
    return value


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the ready-to-send brief for a work item's next unit")
    parser.add_argument("work_item")
    parser.add_argument("--agent", required=True, choices=AGENTS)
    parser.add_argument("--commits", help="revision or range the review/test brief reads")
    parser.add_argument("--report", help="the implementing agent's report-back (FILE or text:BODY)")
    parser.add_argument("--traceability", help="the traceability map (FILE or text:BODY)")
    parser.add_argument("--findings", help="accepted non-blocking review findings (FILE or text:BODY)")
    parser.add_argument(
        "--file", action="store_true",
        help="write to {TEMPDIR}/{repo}-prompt-{work item}.md and print that path instead of stdout",
    )
    args = parser.parse_args(command_args)

    try:
        output = build(args.work_item, args.agent, args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    if args.file:
        print(write_scratch(scratch_path(f"prompt-{args.work_item}"), output))
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
