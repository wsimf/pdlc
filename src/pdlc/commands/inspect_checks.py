#!/usr/bin/env python3
"""NAME
    pdlc inspect checks - read-only: every CI check on a work item's pull requests

USAGE
    pdlc inspect checks WORK_ITEM

DESCRIPTION
    Lists every CI check on the head commit of each pull request registered on
    the work item: its state, its name, and a link to its run or details page.

    Each pull request's heading carries its overall check state, the same one
    the CI gate reads. A rerun supersedes the earlier run of the same check, so
    only the current result is listed. Checks matching the configured ignore
    patterns (`pdlc config ignored_checks`) are left out of that state and of
    the per-PR list, and are named under `## Ignored checks` instead; their
    failures are never a reason to fix, rerun, or report anything.

        # Checks — #18

        ## PR #149 — FAILURE
        https://github.com/acme/app/pull/149

        - FAILURE: CI / unit — https://github.com/acme/app/actions/runs/7/job/42
        - SUCCESS: CI / lint — https://github.com/acme/app/actions/runs/7/job/43

        ## PR #150 — NONE
        https://github.com/acme/app/pull/150

        No checks.

        ## Ignored checks

        Checks matching `Nightly` are intentionally marked as ignored by the user; any failure on them is discarded — do not investigate, rerun, fix, or report it.

        - PR #149: Nightly / e2e

    A GitHub Actions check's link ends in `runs/RUN_ID/job/JOB_ID`; `gh run
    view --job JOB_ID --log-failed` prints just that job's failure. With no registered
    pull request it prints `No pull requests are registered on #<n>.` The
    command writes nothing.

EXAMPLES
    pdlc inspect checks 18
"""

from __future__ import annotations

import argparse
import sys

from pdlc.config import get_config
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.records import CheckResult, pull_ref, pull_request_label
from pdlc.hosts.code_host import get_code_host
from pdlc.internal.failure import report_failure
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.pull_requests import record_pull_requests


def render(issue: str, results: list[tuple[dict, list[CheckResult]]], patterns: tuple[str, ...]) -> str:
    lines = [f"# Checks — #{issue}"]
    if not results:
        lines += ["", f"No pull requests are registered on #{issue}."]
    ignored: list[str] = []
    for pr, checks in results:
        label = pull_request_label(pr)
        lines += ["", f"## PR {label} — {pr.get('checks')}", pr["url"], ""]
        kept = [check for check in checks if not check["ignored"]]
        ignored += [f"- PR {label}: {check['name']}" for check in checks if check["ignored"]]
        if not kept:
            lines.append("No checks.")
        for check in kept:
            lines.append(f"- {check['state']}: {check['name']}" + (f" — {check['url']}" if check["url"] else ""))
    if patterns:
        listed = ", ".join(f"`{pattern}`" for pattern in patterns)
        lines += [
            "",
            "## Ignored checks",
            "",
            f"Checks matching {listed} are intentionally marked as ignored by the user; "
            "any failure on them is discarded — do not investigate, rerun, fix, or report it.",
        ]
        if ignored:
            lines += ["", *ignored]
    return "\n".join(lines) + "\n"


def inspect_checks(issue: str) -> str:
    code_host = get_code_host()
    results = [(pr, code_host.pull_request_checks(pull_ref(pr))) for pr in record_pull_requests(issue)]
    return render(issue, results, get_config().ignored_checks)


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="List every CI check on a work item's pull requests")
    parser.add_argument("work_item")
    args = parser.parse_args(command_args)

    try:
        sys.stdout.write(inspect_checks(args.work_item))
    except PdlcError as error:
        return report_failure(error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
