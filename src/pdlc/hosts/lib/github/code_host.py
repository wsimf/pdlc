"""GitHub code host: pull requests registered on a record and their check rollup.

Which pull requests belong to a record is decided by the explicit registry on
the work item and its delivery tasks (see `internal.pull_requests`), not by a
`Closes #N` keyword or a branch name. This host fetches PR state by number and
delegates the stacked-task flow wholesale to the `gh stack` extension: `gh stack`
owns the stack's order, bases, rebases, and which branches have landed. Nothing
here re-derives that from remote branch listings or branch names.

`unresolved_review_comments` reads live review-thread state via GraphQL —
`isResolved` is not exposed by `gh pr view --json`, only by the review-threads
connection. `pull_requests_by_number` reads every registered PR in one aliased
GraphQL query, so a record's N pull requests cost one round trip, not N.
"""

from __future__ import annotations

import contextlib
import re

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
from pdlc.hosts.lib.process import run_process
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

# The GraphQL selection behind `_PR_FIELDS`: the head commit's check rollup
# carries the same CheckRun (`status`/`conclusion`) and StatusContext (`state`)
# entries `gh pr view --json statusCheckRollup` lists, so `_checks_state` reads
# either source unchanged.
_PR_SELECTION = """
number title url state isDraft headRefName headRefOid mergedAt
commits(last: 1) { nodes { commit { statusCheckRollup { contexts(first: 100) {
  pageInfo { hasNextPage }
  nodes { ... on CheckRun { status conclusion } ... on StatusContext { state } }
} } } } }
"""

# gh/GraphQL phrasings that mean "this PR number or branch has no pull request",
# as opposed to auth expiry, rate limiting, or a network failure — which must
# propagate so a transient error is never read as "PR not registered".
_PR_NOT_FOUND = ("could not resolve to a pullrequest", "no pull requests found", "no pull request found")

# A batched query fails as a whole when one alias misses; GraphQL names that
# alias's number in the error, which `gh` passes through on stderr.
_MISSING_PR_NUMBER = re.compile(r"could not resolve to a pullrequest with the number of (\d+)", re.IGNORECASE)


def _is_pr_not_found(error: PdlcError) -> bool:
    message = str(error).lower()
    return any(phrase in message for phrase in _PR_NOT_FOUND)


def _local_branch_exists(branch: str) -> bool:
    """Whether ``branch`` is already a local ref. Only asked when the task has
    no pull request to check out from — an implemented-but-unsubmitted task."""
    try:
        run_process(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"])
    except PdlcError:
        return False
    return True


def _graphql_rollup(pull_request: dict) -> list[dict] | None:
    """The head commit's check contexts in `gh pr view` shape, `[]` when the
    commit has no rollup, or None when more than one page of contexts exists
    and only `gh pr view`'s own pagination can see them all."""
    commits = (pull_request.get("commits") or {}).get("nodes") or []
    rollup = (commits[0].get("commit") or {}).get("statusCheckRollup") if commits else None
    if rollup is None:
        return []
    contexts = rollup.get("contexts") or {}
    if (contexts.get("pageInfo") or {}).get("hasNextPage"):
        return None
    return list(contexts.get("nodes") or [])


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
        if not numbers:
            return []
        owner, repository = owner_repository()
        selections = "\n".join(
            f"pr{index}: pullRequest(number: {int(number)}) {{ {_PR_SELECTION} }}"
            for index, number in enumerate(numbers)
        )
        query = f"query($owner: String!, $repo: String!) {{ repository(owner: $owner, name: $repo) {{\n{selections}\n}} }}"
        try:
            data = run_graphql(query, owner=owner, repo=repository)["data"]["repository"]
        except PdlcError as error:
            if _is_pr_not_found(error):
                match = _MISSING_PR_NUMBER.search(str(error))
                missing = f"#{match.group(1)}" if match else "among " + ", ".join(f"#{number}" for number in numbers)
                raise PdlcError(f"registered pull request {missing} could not be found") from error
            raise PdlcError(f"could not resolve pull requests {', '.join(f'#{number}' for number in numbers)}: {error}") from error
        resolved = []
        for index, number in enumerate(numbers):
            pr = data.get(f"pr{index}")
            if pr is None:
                raise PdlcError(f"registered pull request #{number} could not be found")
            rollup = _graphql_rollup(pr)
            resolved.append(_pr_dict({**pr, "statusCheckRollup": rollup}) if rollup is not None else self._pull_request_view(number))
        return resolved

    @staticmethod
    def _pull_request_view(number: int) -> PullRequest:
        try:
            pr = run_gh_json(["pr", "view", str(number), *repo_args(), "--json", _PR_FIELDS])
        except PdlcError as error:
            if _is_pr_not_found(error):
                raise PdlcError(f"registered pull request #{number} could not be found") from error
            raise PdlcError(f"could not resolve pull request #{number}: {error}") from error
        return _pr_dict(pr)

    def pull_request_files(self, pr_number: str | int) -> list[str]:
        data = run_gh_json(["pr", "view", str(pr_number), *repo_args(), "--json", "files"])
        return [entry["path"] for entry in data.get("files", [])]

    def checkout_task_branch(self, branch: str, pr: int | None, entry_pr: int | None) -> str:
        # `gh stack checkout` takes either a pull request or a branch and
        # fetches the rest of the stack from GitHub itself, so a fresh clone
        # needs no local tracking to land on the right branch. The PR is
        # preferred over the branch for exactly that reason: the branch may not
        # exist locally yet.
        self._require_stack_extension()
        if pr is not None:
            run_gh(["stack", "checkout", str(pr)])
            return f"checked out {branch} from its pull request #{pr}"
        if _local_branch_exists(branch):
            run_gh(["stack", "checkout", branch])
            return f"checked out the existing local branch {branch}"
        if entry_pr is not None:
            run_gh(["stack", "checkout", str(entry_pr)])
            run_gh(["stack", "add", branch])
            return f"created {branch} on the stack entered at pull request #{entry_pr}"
        if self._current_stack() is not None:
            # `gh stack add` only extends a stack from its top branch.
            run_gh(["stack", "top"])
            run_gh(["stack", "add", branch])
            return f"created {branch} on top of the stack the current branch belongs to"
        run_gh(["stack", "init", branch])
        return f"created {branch} as the first branch of a new stack"

    @staticmethod
    def _current_stack() -> dict | None:
        """The local stack the current branch belongs to, as `gh stack view
        --json` reports it, or None when it belongs to none. A work item's first
        task continues that stack rather than starting a new one, so it can
        build on another work item's unmerged stack in the same checkout.

        `gh stack view` exits non-zero off a stack; a missing extension fails
        the same way and is left for the acting call to report."""
        try:
            data = run_gh_json(["stack", "view", "--json"])
        except PdlcError:
            return None
        return data if isinstance(data, dict) and data.get("branches") else None

    def submit_task_stack(self) -> list[PullRequest]:
        """Restack, push, and create/update the current local stack's pull requests.

        Trunk is left alone unless a task below has landed: a new commit on
        trunk never rebases the stack. The restack is `gh stack rebase
        --no-trunk`, which only rebases each branch onto its parent, without
        fetching. A stack PR that GitHub reports merged while its branch is
        still local is the one case that needs trunk: `gh stack sync --prune`
        fetches, rebases the branches above onto trunk (dropping the landed
        commits), and deletes the merged branch, so the next submit is back on
        the trunk-free path. `gh stack submit --auto` then pushes and creates or
        updates one PR per branch with the bases already chained.
        """

        self._require_stack_extension()
        if self._has_unpruned_merge():
            run_gh(["stack", "sync", "--prune"])
        else:
            try:
                run_gh(["stack", "rebase", "--no-trunk"])
            except PdlcError:
                # A conflict stops mid-rebase; restore every branch, as sync
                # would, so a failed post leaves the stack untouched. A failure
                # before any rebase started has nothing to abort.
                with contextlib.suppress(PdlcError):
                    run_gh(["stack", "rebase", "--abort"])
                raise
        run_gh(["stack", "submit", "--auto"])
        return self.pull_requests_by_number(self.stack_pr_numbers())

    def _has_unpruned_merge(self) -> bool:
        """Whether a stack PR has merged on GitHub while its branch is still
        local. Merge state is read live rather than from `gh stack view`, which
        may lag until the next sync."""
        return any(
            pr["state"] == "MERGED" and _local_branch_exists(pr["branch"])
            for pr in self.pull_requests_by_number(self.stack_pr_numbers())
        )

    def link_task_stack(self, entry_pr: int, branch: str) -> PullRequest:
        # `gh stack checkout <entry_pr>` (the ordinary `checkout_task_branch` path)
        # would `git checkout` the predecessor's branch, which fails when that
        # branch is checked out in the predecessor's own, still-active
        # worktree. `gh stack link` needs no local tracking of the predecessor
        # at all: renaming the current branch (already sitting on the
        # predecessor's tip) to its deterministic task name, then linking it
        # onto `entry_pr`, pushes it and creates its pull request chained onto
        # the predecessor without ever touching the predecessor's branch.
        self._require_stack_extension()
        run_process(["git", "branch", "-m", branch])
        run_gh(["stack", "link", str(entry_pr), branch])
        return self._pull_request_view_by_branch(branch)

    @staticmethod
    def _pull_request_view_by_branch(branch: str) -> PullRequest:
        try:
            pr = run_gh_json(["pr", "view", branch, *repo_args(), "--json", _PR_FIELDS])
        except PdlcError as error:
            if _is_pr_not_found(error):
                raise PdlcError(f"no pull request found for {branch} after linking it into the stack") from error
            raise PdlcError(f"could not resolve pull request for {branch}: {error}") from error
        return _pr_dict(pr)

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
