"""Open change requests: what a stage has been asked to change since it last
published.

A change request is a marked record comment that asks a stage for rework:

- a `PDLC-REVIEW` with a Changes Required or Decision Required verdict, owned
  by its `bounce` stage when it bounces and by its `stage` otherwise;
- a `PDLC-REVIEW` CI-failure note, owned by its `CI failed stage:` line;
- a `PDLC-RESOLUTION`, owned by its `Resolved stage:` line;
- a `PDLC-INVALIDATED`, owned by its `Invalidated stage:` line.

`PDLC-DECISION` is skipped: its text is already inside the decision-required
review posted with it.

A request is open while its stage has not published since. Publishing is the
stage's claim that it addressed everything asked of it, and the next review
re-checks that claim. Verification publishes as a `PDLC-REVIEW` itself, so its
own Changes Required or Decision Required review both publishes and requests,
and stays open.

Comments written before the stage lines existed fall back to inference: a
resolution belongs to the newest decision-required review before it, and a CI
note to the stage its sentence names. Nothing here does I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pdlc.domain.evidence import ReviewVerdict, parse_review
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import marked_comments
from pdlc.domain.workflow import Pipeline

_CI_STAGE_LINE = re.compile(r"^CI failed stage:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_RESOLVED_STAGE_LINE = re.compile(r"^Resolved stage:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_INVALIDATED_STAGE_LINE = re.compile(r"^Invalidated stage:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_LEGACY_CI_SENTENCE = re.compile(r"CI check has failed on the (.+?) pull request")


# How each request source reads to a person or agent, shared by
# `pdlc inspect changes` and the Due Next `### Open Changes` summary.
SOURCE_LABELS = {
    "review": "Review findings",
    "decision": "Review decision",
    "bounce": "Verification bounce",
    "ci": "CI failure",
    "resolution": "Decision resolution",
    "invalidation": "Invalidation",
}


@dataclass(frozen=True)
class ChangeRequest:
    stage: str
    source: str  # review | decision | bounce | ci | resolution | invalidation
    comment: dict[str, Any]


@dataclass(frozen=True)
class OpenChanges:
    stage: str
    published: dict[str, Any] | None  # the stage's latest publication comment
    requests: tuple[ChangeRequest, ...]


def _stage_named(pipeline: Pipeline, name: str | None) -> str | None:
    if not name:
        return None
    wanted = name.strip().lower()
    return next((stage for stage in pipeline.all_stage_names if stage.lower() == wanted), None)


def _line(pattern: re.Pattern[str], body: str) -> str | None:
    match = pattern.search(body)
    return match.group(1) if match else None


def open_change_requests(comments: list[dict[str, Any]], pipeline: Pipeline, stage: str) -> OpenChanges:
    """The change requests `stage` has received since its latest publication,
    oldest first. A stage that never published has every request open."""
    marker = pipeline.marker_for_stage(stage)
    published_at: int | None = None
    requests: list[tuple[int, ChangeRequest]] = []
    decision_stage: str | None = None
    tagged = marked_comments(comments)

    for index, comment in enumerate(tagged):
        body = comment["body"]
        kind = comment["marker"]
        if kind == "REVIEW":
            try:
                review = parse_review(body)
            except PdlcError:
                owner = _stage_named(pipeline, _line(_CI_STAGE_LINE, body) or _line(_LEGACY_CI_SENTENCE, body))
                if owner:
                    requests.append((index, ChangeRequest(owner, "ci", comment)))
                continue
            if marker == "REVIEW" and review.stage == stage:
                published_at = index
            if review.verdict == ReviewVerdict.DECISION_REQUIRED:
                decision_stage = review.stage
                requests.append((index, ChangeRequest(review.stage, "decision", comment)))
            elif review.verdict == ReviewVerdict.CHANGES_REQUIRED:
                source = "bounce" if review.bounce else "review"
                requests.append((index, ChangeRequest(review.bounce or review.stage, source, comment)))
        elif kind == "RESOLUTION":
            owner = _stage_named(pipeline, _line(_RESOLVED_STAGE_LINE, body)) or decision_stage
            if owner:
                requests.append((index, ChangeRequest(owner, "resolution", comment)))
        elif kind == "INVALIDATED":
            owner = _stage_named(pipeline, _line(_INVALIDATED_STAGE_LINE, body))
            if owner:
                requests.append((index, ChangeRequest(owner, "invalidation", comment)))
        elif kind == marker:
            published_at = index

    open_requests = tuple(
        request
        for index, request in requests
        if request.stage == stage and (published_at is None or index >= published_at)
    )
    published = tagged[published_at] if published_at is not None else None
    return OpenChanges(stage, published, open_requests)


def open_changes_summary(changes: OpenChanges) -> str:
    """One line counting the open requests by source, in first-seen order:
    `3 open change requests for Implementation: Review findings (2), CI failure.`"""
    counts: dict[str, int] = {}
    for request in changes.requests:
        counts[request.source] = counts.get(request.source, 0) + 1
    kinds = ", ".join(SOURCE_LABELS[source] + (f" ({count})" if count > 1 else "") for source, count in counts.items())
    total = len(changes.requests)
    noun = "request" if total == 1 else "requests"
    return f"{total} open change {noun} for {changes.stage}: {kinds}."
