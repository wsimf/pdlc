#!/usr/bin/env python3
"""NAME
    pdlc prompt - read-only: print the ready-to-send brief for a work item's next unit

USAGE
    pdlc prompt COMMAND WORK_ITEM [flags]

COMMANDS
    task-implementer   brief the sub-agent that writes one delivery task's code
    task-reviewer      brief the reviewer that reads one dispatch's commits
    task-test-writer   brief the test writer that covers one dispatch's change

DESCRIPTION
    Prints one complete sub-agent brief for the unit of work a record has next,
    with every value already filled in. The output is sent to the sub-agent
    verbatim: it carries the task, its plan, the covered requirements, and the
    boundaries the agent works inside, and it names no PDLC command, stage, or
    gate.

    Every command above describes the same unit, so the implementer, the
    reviewer, and the test writer are held to one task, one plan, and one set
    of acceptance criteria on a given pass. They differ only in what each
    sub-agent needs that the record cannot supply, which is why they take
    different flags.

    Nothing due prints what the record is waiting on and exits non-zero, so a
    caller never dispatches an agent against an empty unit. Every command reads
    the record and its live pull-request state; none of them changes anything.

    A value the record does not carry is reported in place rather than omitted —
    a cited requirement missing from the record's `## Product` renders as "not
    found" inside the brief instead of leaving the agent a hole it cannot see.

EXAMPLES
    pdlc prompt task-implementer 236
    pdlc prompt task-reviewer 236 --commits HEAD~2..HEAD

LEARN MORE
    Run `pdlc prompt COMMAND --help` for that command's own usage and flags.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
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

BRIEF_COMMANDS = ("task-implementer", "task-reviewer", "task-test-writer")


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


def implementer_brief(work_item: str) -> str:
    """The brief for the sub-agent writing this pass's code."""
    return _implementer_brief(_resolve(work_item))


def reviewer_brief(work_item: str, commits: str) -> str:
    """The brief for the reviewer reading `commits` against this pass's task."""
    return _review_brief(_resolve(work_item), commits)


def test_writer_brief(
    work_item: str, commits: str, report: str, traceability: str, findings: str | None,
) -> str:
    """The brief for the test writer covering what `commits` changed."""
    return _test_brief(
        _resolve(work_item),
        commits,
        resolve_text(report, label="--report"),
        resolve_text(traceability, label="--traceability"),
        resolve_text(findings, label="--findings") if findings else "",
    )


def add_common_arguments(parser: argparse.ArgumentParser, command: str) -> None:
    """The work item and `--file`, which every brief command takes alike."""
    parser.add_argument("work_item")
    parser.add_argument(
        "--file", action="store_true",
        help=f"write to {{TEMPDIR}}/{{repo}}-prompt-{command}-{{work item}}.md and print that path",
    )


def emit(brief: str, work_item: str, command: str, to_file: bool) -> None:
    """Print the brief, or the path of the scratch file now holding it.

    The command name is part of that path so one pass's three briefs cannot
    overwrite each other: a caller that still held the implementer's path would
    otherwise read the reviewer's brief back out of it.
    """
    if to_file:
        print(write_scratch(scratch_path(f"prompt-{command}-{work_item}"), brief))
    else:
        sys.stdout.write(brief)


def run(command: str, args: argparse.Namespace, build: Callable[[], str]) -> int:
    """Render one brief, reporting a refusal without writing or printing it."""
    try:
        brief = build()
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    emit(brief, args.work_item, command, args.file)
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
