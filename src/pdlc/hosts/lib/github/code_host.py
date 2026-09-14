"""GitHub code host: pull requests registered on a record and their check rollup.

Which pull requests belong to a record is decided by the explicit registry on
the work item and its delivery tasks (see `internal.pull_requests`), not by a
`Closes #N` keyword or a branch name. This host fetches PR state by number and
delegates the stacked-task flow wholesale to the `gh stack` extension: `gh stack`
owns the stack's order, bases, rebases, and which branches have landed. Nothing
here re-derives that from remote branch listings or branch names.

`unresolved_review_comments` reads live review-thread state via GraphQL —
`isResolved` is not exposed by `gh pr view --json`, only by the review-threads
connection, so this is the one query in the module that doesn't go through
`run_gh_json`.
"""

from __future__ import annotations

from pdlc.domain.records import PullRequest, ReviewComment


from pdlc.hosts.code_host.base import CodeHost
from pdlc.hosts.lib.github.transport import (
    body_file,
    owner_repository,
    repo_args,
    run_gh,
    run_gh_json,
    run_graphql,
)
from pdlc.domain.lifecycle import PdlcError

# Every review thread on the pull request, oldest first, with only its root
# comment — later replies aren't fetched, since the thread's own `isResolved`
# already carries the "is this settled" signal a reply would otherwise stand
# in for.
_REVIEW_THREADS_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          isResolved
          comments(first: 1) {
            nodes { body url path line author { login } }
          }
        }
      }
    }
  }
}
"""

_STACK_MISSING = (
    "the `gh stack` extension is required for stacked task pull requests — "
    "install it with `gh extension install github/gh-stack`"
)

_PR_FIELDS = "number,title,url,state,isDraft,headRefName,headRefOid,mergedAt,statusCheckRollup"

# gh/GraphQL phrasings that mean "this PR number or branch has no pull request",
# as opposed to auth expiry, rate limiting, or a network failure — which must
# propagate so a transient error is never read as "PR not registered".
_PR_NOT_FOUND = ("could not resolve to a pullrequest", "no pull requests found", "no pull request found")


def _is_pr_not_found(error: PdlcError) -> bool:
    message = str(error).lower()
    return any(phrase in message for phrase in _PR_NOT_FOUND)


def _checks_state(pull_request: dict) -> str:
    # `gh pr view --json statusCheckRollup` exposes a union list directly on
    # the pull request: CheckRun entries use `conclusion`, StatusContext
    # entries use `state`.
    rollup = pull_request.get("statusCheckRollup")
    if rollup is None:
        return "NONE"
    if isinstance(rollup, dict):
        return "PENDING"
    if isinstance(rollup, list):
        if not rollup:
            return "NONE"
        states = []
        malformed = False
        for entry in rollup:
            if not isinstance(entry, dict):
                malformed = True
                continue
            if "status" in entry:
                if entry.get("status") != "COMPLETED" or not entry.get("conclusion"):
                    states.append("PENDING")
                    continue
                state = entry.get("conclusion")
            elif "state" in entry:
                state = entry.get("state")
            else:
                malformed = True
                continue
            if state:
                states.append(state)
            else:
                malformed = True
        if malformed:
            return "PENDING"
        if any(state in ("FAILURE", "ERROR", "FAIL", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED") for state in states):
            return "FAILURE"
        if any(state in ("PENDING", "EXPECTED", "QUEUED", "IN_PROGRESS", "WAITING") for state in states):
            return "PENDING"
        return "SUCCESS" if all(state in ("SUCCESS", "NEUTRAL", "SKIPPED") for state in states) else "PENDING"
    return "PENDING"


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
        "headSha": pr.get("headRefOid") or "",
    }


class GitHubCodeHost(CodeHost):
    def ensure_pull_request_linked(self, code_ref: str) -> PullRequest:
        try:
            # No PR number and no `--repo`: `gh pr view` must resolve the current
            # branch's PR from the local checkout, and gh (>=2.98) rejects the
            # branch fallback when `--repo` is also passed.
            pull_request = run_gh_json(["pr", "view", "--json", _PR_FIELDS])
        except PdlcError as error:
            if _is_pr_not_found(error):
                raise PdlcError("no pull request exists for the current branch") from error
            raise
        if not pull_request.get("number"):
            raise PdlcError("current branch pull request has no number")
        return _pr_dict(pull_request)

    def pull_requests_by_number(self, numbers: list[int]) -> list[PullRequest]:
        resolved = []
        for number in numbers:
            try:
                pr = run_gh_json(["pr", "view", str(number), *repo_args(), "--json", _PR_FIELDS])
            except PdlcError as error:
                if _is_pr_not_found(error):
                    raise PdlcError(f"registered pull request #{number} could not be found") from error
                raise PdlcError(f"could not resolve pull request #{number}: {error}") from error
            resolved.append(_pr_dict(pr))
        return resolved

    def pull_request_files(self, pr_number: str | int) -> list[str]:
        data = run_gh_json(["pr", "view", str(pr_number), *repo_args(), "--json", "files"])
        return [entry["path"] for entry in data.get("files", [])]

    def task_stack_setup(self, branch: str, entry_pr: int | None) -> list[str]:
        # `gh stack` owns the stack's order, bases, and rebases, so nothing here
        # computes a base branch or asks whether a predecessor's branch still
        # exists: `gh stack checkout <pr>` fetches the stack from GitHub itself.
        if entry_pr is None:
            return [f"stackSetup: gh stack init {branch}  (first task — creates the stack on the default branch)"]
        return [
            f"stackSetup: gh stack checkout {entry_pr} && gh stack add {branch}",
            f"stackEntryPr: {entry_pr}  (the previous implemented task's registered PR)",
        ]

    def submit_task_stack(self) -> list[PullRequest]:
        """Sync, push, and create/update the current local stack's pull requests.

        `gh stack sync --prune` is the extension's own answer to "a task below
        this one has landed": it fetches, cascade-rebases each branch onto its
        updated parent, pushes, and drops local branches whose PR merged. PDLC
        never inspects remote branch existence to work that out. `gh stack
        submit --auto` then creates or updates one PR per branch with the bases
        already chained.
        """

        self._require_stack_extension()
        run_gh(["stack", "sync", "--prune"])
        run_gh(["stack", "submit", "--auto"])
        return self.pull_requests_by_number(self.stack_pr_numbers())

    def set_pull_request_content(self, number: int, title: str, body: str) -> None:
        # `gh pr edit --title --body-file` replaces both fields wholesale. This
        # runs after `submit_task_stack`, and `gh stack` only writes a PR's title
        # and body when it first creates the PR, never on a later sync/submit, so
        # the task's own title and evidence stay the PR's resting state.
        with body_file(body) as path:
            run_gh(["pr", "edit", str(number), *repo_args(), "--title", title, "--body-file", path])

    def mark_pull_requests_ready(self, numbers: list[int]) -> None:
        # `gh pr ready` on a PR that is already out of draft is a no-op that
        # still exits 0, so republishing after a `Changes Required` bounce needs
        # no guard here. The caller filters out merged/closed numbers, which
        # `gh pr ready` would otherwise reject.
        for number in numbers:
            run_gh(["pr", "ready", str(number), *repo_args()])

    def unresolved_review_comments(self, pr_number: str | int) -> list[ReviewComment]:
        owner, repository = owner_repository()
        data = run_graphql(_REVIEW_THREADS_QUERY, owner=owner, repo=repository, number=int(pr_number))
        threads = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
        comments = []
        for thread in threads:
            if thread.get("isResolved"):
                continue
            nodes = thread.get("comments", {}).get("nodes") or []
            if not nodes:
                continue
            root = nodes[0]
            comments.append({
                "author": (root.get("author") or {}).get("login") or "unknown",
                "body": root.get("body") or "",
                "url": root.get("url"),
                "path": root.get("path"),
                "line": root.get("line"),
            })
        return comments

    @staticmethod
    def stack_pr_numbers() -> list[int]:
        """The pull-request numbers in the current local stack, bottom-to-top,
        as `gh stack view --json` reports them.

        Only `branches[].pr.number` is read from that payload — `pr` is absent
        for a branch with no pull request yet. Every other PR field comes from
        `pull_requests_by_number`, so one canonical dict shape serves every
        caller and this stays insensitive to the rest of the extension's JSON.
        """
        data = run_gh_json(["stack", "view", "--json"])
        return [
            int(branch["pr"]["number"])
            for branch in (data.get("branches") or [])
            if isinstance(branch.get("pr"), dict) and branch["pr"].get("number") is not None
        ]

    @staticmethod
    def _require_stack_extension() -> None:
        installed = run_gh(["extension", "list"])
        if "github/gh-stack" not in installed:
            raise PdlcError(_STACK_MISSING)
