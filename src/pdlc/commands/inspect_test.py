#!/usr/bin/env python3
"""NAME
    pdlc inspect test - read-only: whether testing is due and the testable scope

USAGE
    pdlc inspect test WORK_ITEM

DESCRIPTION
    Step 1-3 of pdlc-test in one call. Checks whether coverage is
    actually due right now, then — only if it is — resolves the testable scope:
    every delivery task that closed with its implementation recorded, its linked
    PRs, and the files those PRs actually touched (from the merge commit, since
    implementation routinely touches files the write-up never mentions). The
    agent still reads the implementation write-ups and the touched source for
    behaviour and real API signatures; this stops short of that judgment.

    ## Readiness

    Ready — Gate State: Pending.

    ## Testable Scope

    ### WORK-142-TASK-003 [CORE] Persist profile geometry

    PR #148 (MERGED, checks: SUCCESS)
    Files touched:
    - src/services/profile_store.py
    - src/models/profile.py

or, when not ready:

    ## Readiness

    Not ready: Status is 'Implementation', not Testing. That stage owns this Work Item now.

Testable Scope reads "No task has closed with a Result yet — nothing is
implemented." when there's nothing in scope.
"""

from __future__ import annotations

import sys


from pdlc.hosts.code_host import get_code_host
from pdlc.internal.attachments import attachments_for_item, attachments_markdown
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, wants_help
from pdlc.internal.pull_requests import record_pull_requests
from pdlc.internal.workitem import due_next, resolve_item, task_tree


# A PR's touched files, straight from the code host rather than guessed from
# local git state — the same set whether the PR is merged, still open, or the
# worktree hasn't fetched its branch at all.
def _files_for_pull_request(pr: dict) -> list[str]:
    return get_code_host().pull_request_files(pr["number"])


def _testable_scope_section(tasks: list[dict], pull_requests: list[dict]) -> list[str]:
    in_scope = [t for t in tasks if t["state"] == "CLOSED" and t["hasImplementation"]]
    if not in_scope:
        return ["## Testable Scope", "", "No task has closed with its implementation recorded yet — nothing is implemented."]

    pr_by_number = {pr["number"]: pr for pr in pull_requests}
    files_by_number: dict[int, list[str]] = {}

    sections = ["## Testable Scope"]
    for task in in_scope:
        sections += ["", f"### {task['title']}"]
        # A task's scope is its explicitly registered PRs. The record-level
        # registry may include PRs for sibling tasks and must not leak them
        # into every testing prompt.
        task_prs = [pr_by_number[number] for number in task.get("prs", []) if number in pr_by_number]
        for pr in task_prs:
            if pr["number"] not in files_by_number:
                files_by_number[pr["number"]] = _files_for_pull_request(pr)
            files = files_by_number[pr["number"]]
            sections += [
                "",
                f"PR #{pr['number']} ({pr['state']}, checks: {pr['checks']})",
                "Files touched:" if files else "Files touched: none found — inspect the PR diff directly.",
            ]
            sections += [f"- {f}" for f in files]

    return sections


def _readiness(item: dict) -> tuple[bool, str]:
    status = item.get("Status")
    gate = item.get("Gate State")

    if status != "Testing":
        return False, f"Not ready: Status is {status!r}, not Testing. That stage owns this Work Item now."

    due = due_next(item)
    if due["action"] != "pdlc-test":
        return False, f"Not ready: Gate State is {gate!r}. {due['reason'].capitalize()}."

    return True, f"Ready — Gate State: {gate}."


def inspect(issue: str) -> str:
    item = resolve_item(issue)
    ready, readiness_message = _readiness(item)
    sections = ["## Readiness", "", readiness_message, "", attachments_markdown(attachments_for_item(item))]
    if not ready:
        return "\n".join(sections) + "\n"

    tasks = task_tree(issue)
    pull_requests = record_pull_requests(issue, record=item, tasks=tasks)

    sections += ["", *_testable_scope_section(tasks, pull_requests)]

    return "\n".join(sections) + "\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    args = command_args
    if wants_help(args):
        print_help(__doc__)
        return 0
    if len(args) != 1:
        print("usage: pdlc inspect test WORK_ITEM", file=sys.stderr)
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
