#!/usr/bin/env python3
"""Read-only: Step 1-2 of pdlc-review in one call. Checks whether review is
actually due right now, then — only if it is — names the exact artifact
under review and the reviewer agent that owns it, so the agent never has to
re-apply the Status→artifact→reviewer table by hand. Also flags a stage that
reached Review Required but shouldn't have (Product/Verification never do;
UI/Tasks/Technical Plan are reviewed locally before publication) and a stage
listed in Skipped States, which pdlc-post-review.py refuses to review.

    pdlc-inspect-review.py WORK_ITEM

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
from pathlib import Path


from pdlc.internal.attachments import attachments_for_item, attachments_markdown  # type: ignore
from pdlc.internal.workitem import is_stage_skipped, resolve_item  # type: ignore
from pdlc.domain.lifecycle import PdlcError, print_help, wants_help  # type: ignore

# Status → (artifact under review, reviewer agent). Product and Verification
# never reach Review Required — Product is reviewed locally by pdlc-write
# before publication, and Verification records its own outcome — so they
# carry no entry here.
_REVIEW_TARGETS = {
    "UI": ("The parent's UI section and its UJ-* journeys", "pdlc-tasks-reviewer"),
    "Tasks": ("The delivery tasks", "pdlc-tasks-reviewer"),
    "Technical Plan": ("The Technical Plan on each incomplete task", "pdlc-plan-reviewer"),
    "Implementation": ("Production PRs and each task's implementation", "pdlc-implementation-reviewer"),
    "Testing": ("Test PRs, coverage, and requirement traceability", "pdlc-testing-reviewer"),
}


def _readiness(item: dict) -> tuple[bool, str]:
    status = item.get("Status")
    gate = item.get("Gate State")

    if gate == "Decision Required":
        return False, "Not ready: Gate State is 'Decision Required' — a prior review raised a blocking finding the driver must resolve (see the PDLC-DECISION comment) before review can resume."

    if gate == "CI Pending":
        return False, "Not ready: Gate State is 'CI Pending' — the implementation review already passed; the record is waiting on the shared PR's CI. pdlc-post-ci.py resolves it once checks finish (see references/resolve-ci.md)."

    if gate != "Review Required":
        return False, f"Not ready: Gate State is {gate!r}, not Review Required."

    if status in ("Product", "Verification"):
        return False, f"Not ready: {status} never reaches Review Required — something published without going through its owning skill's local review."

    if status not in _REVIEW_TARGETS:
        return False, f"Not ready: no reviewer target for Status {status!r}."

    if is_stage_skipped(item, status):
        return False, f"Not ready: {status} is in this record's Skipped States — pdlc-post-review.py refuses a skipped stage."

    return True, f"Ready — Status: {status}, Gate State: {gate}."


def inspect(issue: str) -> str:
    item = resolve_item(issue)
    ready, readiness_message = _readiness(item)
    sections = ["## Readiness", "", readiness_message, "", attachments_markdown(attachments_for_item(item))]
    if not ready:
        return "\n".join(sections) + "\n"

    artifact, reviewer = _REVIEW_TARGETS[item["Status"]]
    sections += ["", "## Reviewer Target", "", f"Artifact: {artifact}", f"Reviewer agent: {reviewer}"]

    return "\n".join(sections) + "\n"


def main() -> int:
    args = sys.argv[1:]
    if wants_help(args):
        print_help(__doc__)
        return 0
    if len(args) != 1:
        print("usage: pdlc-inspect-review.py WORK_ITEM", file=sys.stderr)
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
