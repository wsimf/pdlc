"""Live PR signals that interrupt approval after PR-backed delivery begins."""

from __future__ import annotations

from dataclasses import dataclass
import re

from pdlc.domain.changes import open_change_requests
from pdlc.domain.stages import Gate
from pdlc.domain.workflow import Pipeline, State
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.ci_gate import check_state
from pdlc.internal.pull_requests import record_open_review_comments, record_pull_requests
from pdlc.internal.workitem import comments_for_issue


@dataclass(frozen=True)
class TriageSignals:
    failed_prs: tuple[dict, ...]
    comments: tuple[dict, ...]

    @property
    def needed(self) -> bool:
        return bool(self.failed_prs or self.comments)


def eligible(pipeline: Pipeline, state: State) -> bool:
    """A PR-backed stage, or any later active stage, may need triage."""
    if state.gate == Gate.DECISION_REQUIRED:
        return False
    stages = pipeline.active_stage_names
    try:
        first = next(index for index, name in enumerate(stages) if pipeline.stage(name).publishes_pull_requests)
        return stages.index(state.stage) >= first
    except (StopIteration, ValueError):
        return False


def signal_ids(signals: TriageSignals) -> tuple[str, ...]:
    return tuple(f"ci:#{pr['number']}:{pr['checks']}" for pr in signals.failed_prs) + tuple(
        f"thread:{comment['url']}" for comment in signals.comments if comment.get("url")
    )


def _handled(comments: list[dict], pipeline: Pipeline, stage: str) -> set[str]:
    requests = open_change_requests(comments, pipeline, stage).requests
    handled: set[str] = set()
    for request in requests:
        if request.source == "ci":
            handled.update(
                f"ci:#{number}:{state}"
                for number, state in re.findall(r"#(\d+)\s+\(([A-Z_]+)\)", request.comment["body"])
            )
            continue
        if request.source != "triage":
            continue
        # Only the command-written header counts; evidence below the first
        # blank line must not be able to suppress a later live signal.
        header = request.comment["body"].split("Triage target stage:", 1)[-1].split("\n\n", 1)[0]
        handled.update(line.removeprefix("Triage signal: ") for line in header.splitlines()
                       if line.startswith("Triage signal: "))
    return handled


def live_signals(issue: str, record: dict, tasks: list[dict], pipeline: Pipeline, state: State, *,
                 pull_requests: list[dict] | None = None, comments: list[dict] | None = None) -> TriageSignals:
    if not eligible(pipeline, state):
        return TriageSignals((), ())
    prs = pull_requests if pull_requests is not None else record_pull_requests(issue, record=record, tasks=tasks)
    failed = tuple(pr for pr in prs if check_state(pr.get("checks")) == "red")
    threads = tuple(record_open_review_comments(issue, record=record, tasks=tasks))
    if any(not thread.get("url") for thread in threads):
        raise PdlcError("code host returned an unresolved review thread without a URL; refusing to triage")
    signals = TriageSignals(failed, threads)
    if state.gate != Gate.CHANGES_REQUIRED or not signals.needed:
        return signals
    handled = _handled(comments if comments is not None else comments_for_issue(issue), pipeline, state.stage)
    return TriageSignals(
        tuple(pr for pr in failed if f"ci:#{pr['number']}:{pr['checks']}" not in handled),
        tuple(thread for thread in threads if f"thread:{thread.get('url')}" not in handled),
    )


def due_next(issue: str, state: State, signals: TriageSignals) -> str:
    lines = ["# Due Next", "", f"Due next: {state.notation} → triage live pull-request signals.",
             "Invoke the `pdlc-triage` skill for this work item."]
    if signals.failed_prs:
        lines += ["", "### CI failures", ""]
        lines += [f"- PR #{pr['number']}: {pr['checks']} ({pr['url']})" for pr in signals.failed_prs]
        lines += ["", "Read `pdlc guide triage-ci-failure` and investigate these failed checks."]
    if signals.comments:
        lines += ["", "### Unresolved review threads", ""]
        lines += [f"- PR #{comment['pr']}: {comment['url']} — {comment['body']}" for comment in signals.comments]
        lines += ["", "Read `pdlc guide triage-pr-review` and judge these threads against current source."]
    lines += ["", "Triage every signal, then use `pdlc post triage " + issue +
              " TARGET EVIDENCE_FILE` to route an actionable change to Implementation or Testing. "
              "Follow the owning stage's normal pipeline from Changes Required. A decision needing the driver stops here."]
    return "\n".join(lines)


def require_clear(signals: TriageSignals) -> None:
    if signals.needed:
        raise PdlcError(
            "live PR signals require triage before approval or completion; "
            "run `pdlc inspect WORK_ITEM` for the CI failures and unresolved review threads"
        )
