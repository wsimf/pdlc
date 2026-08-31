"""GitHub code host: pull requests registered on a record and their check rollup.

Which pull requests belong to a record is decided by the explicit registry on
the work item and its delivery tasks (see `internal.pull_requests`), not by a
`Closes #N` keyword or a branch name. This host fetches PR state by number and
delegates the stacked-task flow wholesale to the `gh stack` extension: `gh stack`
owns the stack's order, bases, rebases, and which branches have landed. Nothing
here re-derives that from remote branch listings or branch names.
"""

from __future__ import annotations

import os

from pdlc.hosts.code_host.base import CodeHost
from pdlc.hosts.github_common import (
    repo_args,
    run_gh,
    run_gh_json,
)
from pdlc.domain.lifecycle import PdlcError

_STACK_MISSING = (
    "the `gh stack` extension is required for stacked task pull requests — "
    "install it with `gh extension install github/gh-stack`"
)

_PR_FIELDS = "number,title,url,state,isDraft,headRefName,mergedAt,commits"

# gh/GraphQL phrasings that mean "this PR number or branch has no pull request",
# as opposed to auth expiry, rate limiting, or a network failure — which must
# propagate so a transient error is never read as "PR not registered".
_PR_NOT_FOUND = ("could not resolve to a pullrequest", "no pull requests found", "no pull request found")


def _is_pr_not_found(error: PdlcError) -> bool:
    message = str(error).lower()
    return any(phrase in message for phrase in _PR_NOT_FOUND)


def _checks_state(pull_request: dict) -> str:
    nodes = (pull_request.get("commits") or {}).get("nodes") or []
    if not nodes:
        return "NONE"
    rollup = (nodes[0].get("commit") or {}).get("statusCheckRollup") or {}
    return rollup.get("state") or "NONE"


def _pr_dict(pr: dict) -> dict:
    return {
        "number": pr["number"],
        "title": pr["title"],
        "url": pr["url"],
        "state": pr["state"],
        "isDraft": pr["isDraft"],
        "branch": pr["headRefName"],
        "mergedAt": pr["mergedAt"],
        "checks": _checks_state(pr),
    }


class GitHubCodeHost(CodeHost):
    def ensure_pull_request_linked(self, code_ref: str) -> dict:
        if os.environ.get("PDLC_ITEMS_FILE"):
            raise PdlcError("cannot resolve a live pull request under a work-item fixture")
        try:
            pull_request = run_gh_json(["pr", "view", *repo_args(), "--json", _PR_FIELDS])
        except PdlcError as error:
            raise PdlcError("no pull request exists for the current branch") from error
        if not pull_request.get("number"):
            raise PdlcError("current branch pull request has no number")
        return _pr_dict(pull_request)

    def pull_requests_by_number(self, numbers: list[int]) -> list[dict]:
        if os.environ.get("PDLC_ITEMS_FILE"):
            return []
        resolved = []
        for number in numbers:
            try:
                pr = run_gh_json(["pr", "view", str(number), *repo_args(), "--json", _PR_FIELDS])
            except PdlcError as error:
                if _is_pr_not_found(error):
                    continue
                raise PdlcError(f"could not resolve pull request #{number}: {error}") from error
            resolved.append(_pr_dict(pr))
        return resolved

    def pull_request_files(self, pr_number: str | int) -> list[str]:
        data = run_gh_json(["pr", "view", str(pr_number), *repo_args(), "--json", "files"])
        return [entry["path"] for entry in data.get("files", [])]

    def submit_task_stack(self) -> list[dict]:
        """Sync, push, and create/update the current local stack's pull requests.

        `gh stack sync --prune` is the extension's own answer to "a task below
        this one has landed": it fetches, cascade-rebases each branch onto its
        updated parent, pushes, and drops local branches whose PR merged. PDLC
        never inspects remote branch existence to work that out. `gh stack
        submit --auto` then creates or updates one PR per branch with the bases
        already chained.
        """
        if os.environ.get("PDLC_ITEMS_FILE"):
            raise PdlcError("cannot submit a stacked pull request under a work-item fixture")

        self._require_stack_extension()
        run_gh(["stack", "sync", "--prune"])
        run_gh(["stack", "submit", "--auto"])
        return self.pull_requests_by_number(self.stack_pr_numbers())

    @staticmethod
    def stack_pr_numbers() -> list[int]:
        """The pull-request numbers in the current local stack, bottom-to-top,
        as `gh stack view --json` reports them.

        Only `branches[].number` is read from that payload; every other PR field
        comes from `pull_requests_by_number`, so one canonical dict shape serves
        every caller and this stays insensitive to the rest of the extension's
        JSON.
        """
        data = run_gh_json(["stack", "view", "--json"])
        return [
            int(entry["number"])
            for entry in (data.get("branches") or [])
            if entry.get("number") is not None
        ]

    @staticmethod
    def _require_stack_extension() -> None:
        try:
            installed = run_gh(["extension", "list"])
        except PdlcError as error:
            raise PdlcError(_STACK_MISSING) from error
        if "github/gh-stack" not in installed:
            raise PdlcError(_STACK_MISSING)
