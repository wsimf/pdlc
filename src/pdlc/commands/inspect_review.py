#!/usr/bin/env python3
"""NAME
    pdlc inspect review - read-only: whether review is due and which artifact/reviewer agent

USAGE
    pdlc inspect review WORK_ITEM

DESCRIPTION
    Step 1-2 of pdlc-review in one call. Checks whether review is
    actually due right now, then — only if it is — names the exact artifact
    under review and the reviewer agent that owns it, so the agent never has to
    re-apply the Status→artifact→reviewer table by hand. Also flags a stage that
    reached Review Required but shouldn't have (Product/Verification never do;
    UI/Tasks/Technical Plan are reviewed locally before publication) and a stage
    listed in Skipped States, which pdlc post review refuses to review.

    ## Readiness

    Ready — Status: Implementation, Gate State: Review Required.

    ## Reviewer Target

    Artifact: Production PRs and each task's implementation
    Reviewer agent: pdlc-implementation-reviewer

or, when not ready:

    ## Readiness

    Not ready: Gate State is 'Pending', not Review Required.
"""

from __future__ import annotations

import sys


from pdlc.internal.attachments import attachments_for_item, attachments_markdown
from pdlc.internal.workitem import is_stage_skipped, resolve_item
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help
from pdlc.domain.workflow import Pipeline
from pdlc.domain.workflows.pipeline import PIPELINES


def _readiness(item: dict, pipeline: Pipeline) -> tuple[bool, str]:
    status = item.get("Status")
    gate = item.get("Gate State")

    if gate == "Decision Required":
        return False, "Not ready: Gate State is 'Decision Required' — a prior review raised a blocking finding the driver must resolve (see last the PDLC-DECISION comment) before review can resume."

    if gate == "CI Pending":
        return False, "Not ready: Gate State is 'CI Pending' — the implementation review already passed; the record is waiting on the registered PR stack's CI. pdlc post ci resolves it once checks finish (see references/resolve-ci.md)."

    if gate != "Review Required":
        return False, f"Not ready: Gate State is {gate!r}, not Review Required."

    try:
        review = pipeline.stage(status).review
    except ValueError:
        return False, f"Not ready: no reviewer target for Status {status!r}."
    if review is None or not review.independent or review.target is None:
        return False, f"Not ready: {status} never reaches Review Required — something published without going through its owning skill's local review."

    if is_stage_skipped(item, status):
        return False, f"Not ready: {status} is in this record's Skipped States — pdlc post review refuses a skipped stage."

    return True, f"Ready — Status: {status}, Gate State: {gate}."


def inspect(issue: str) -> str:
    item = resolve_item(issue)
    try:
        pipeline = PIPELINES.for_record(item)
    except ValueError as error:
        raise PdlcError(str(error)) from None
    ready, readiness_message = _readiness(item, pipeline)
    sections = ["## Readiness", "", readiness_message, "", attachments_markdown(attachments_for_item(item))]
    if not ready:
        return "\n".join(sections) + "\n"

    review = pipeline.stage(item["Status"]).review
    assert review is not None and review.target is not None
    target = review.target
    sections += ["", "## Reviewer Target", "", f"Artifact: {target.artifact}", f"Reviewer agent: {target.agent}"]

    return "\n".join(sections) + "\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    args = command_args
    if wants_help(args):
        print_help(__doc__)
        return 0
    if len(args) != 1:
        print("usage: pdlc inspect review WORK_ITEM", file=sys.stderr)
        return 1
    issue = args[0]

    try:
        output = inspect(issue)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
