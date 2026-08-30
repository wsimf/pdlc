"""GitHub code host: pull requests linked to an Issue and their check rollup."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from pdlc.hosts.code_host.base import CodeHost
from pdlc.hosts.github_common import (
    neutralize_refs,
    owner_repository,
    repo_args,
    run_gh,
    run_gh_json,
    run_graphql,
)
from pdlc.domain.lifecycle import PdlcError

# Pull requests attached to an Issue: those that would close it (linked through
# the Development panel or a closing keyword) plus those that merely reference
# it.
PULL_REQUESTS_QUERY = """
query($owner: String!, $repo: String!, $issue: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $issue) {
      closedByPullRequestsReferences(first: 50, includeClosedPrs: true) {
        nodes { ...pullRequestFields }
      }
      timelineItems(first: 100, itemTypes: [CROSS_REFERENCED_EVENT]) {
        nodes {
          ... on CrossReferencedEvent {
            source { ... on PullRequest { ...pullRequestFields } }
          }
        }
      }
    }
  }
}
fragment pullRequestFields on PullRequest {
  number
  title
  url
  state
  isDraft
  headRefName
  mergedAt
  commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
}
"""


def _checks_state(pull_request: dict) -> str:
    nodes = (pull_request.get("commits") or {}).get("nodes") or []
    if not nodes:
        return "NONE"
    rollup = (nodes[0].get("commit") or {}).get("statusCheckRollup") or {}
    return rollup.get("state") or "NONE"


class GitHubCodeHost(CodeHost):
    def ensure_pull_request_linked(self, code_ref: str) -> dict:
        issue = str(code_ref)
        if not issue.isdigit():
            raise PdlcError(f"code ref must be numeric: {issue}")
        if os.environ.get("PDLC_ITEMS_FILE"):
            raise PdlcError("cannot resolve a live pull request under a work-item fixture")

        try:
            pull_request = run_gh_json([
                "pr", "view", *repo_args(),
                "--json", "number,title,url,state,isDraft,headRefName,mergedAt,commits,body",
            ])
        except PdlcError as error:
            raise PdlcError("no pull request exists for the current branch") from error

        number = pull_request.get("number")
        body = pull_request.get("body") or ""
        if not number:
            raise PdlcError("current branch pull request has no number")

        linked = self.pull_requests(issue)
        existing = next(
            (pr for pr in linked if pr["number"] == number and pr["relation"] == "closes"),
            None,
        )
        if existing:
            return existing

        closing_reference = re.compile(
            rf"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#{re.escape(issue)}\b",
            re.IGNORECASE,
        )
        if not closing_reference.search(body):
            # Neutralize loose refs the PR author left in the body, then append
            # the one deliberate closing reference that links it to the record.
            updated_body = f"{neutralize_refs(body).rstrip()}\n\nCloses #{issue}\n"
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as handle:
                handle.write(updated_body)
                body_path = handle.name
            try:
                run_gh(["pr", "edit", str(number), *repo_args(), "--body-file", body_path])
            finally:
                Path(body_path).unlink(missing_ok=True)

        refreshed = self.pull_requests(issue)
        linked = next(
            (pr for pr in refreshed if pr["number"] == number and pr["relation"] == "closes"),
            None,
        )
        if not linked:
            raise PdlcError(f"pull request #{number} could not be linked to work item #{issue}")
        return linked

    def pull_requests(self, code_ref: str) -> list[dict]:
        issue = str(code_ref)
        if not issue.isdigit():
            raise PdlcError(f"code ref must be numeric: {issue}")

        # Under a work-item fixture there is no live GitHub to query.
        if os.environ.get("PDLC_ITEMS_FILE"):
            return []

        owner, repository = owner_repository()
        data = run_graphql(PULL_REQUESTS_QUERY, owner=owner, repo=repository, issue=int(issue))
        issue_node = data["data"]["repository"]["issue"]

        closes = [
            {**node, "relation": "closes"}
            for node in issue_node["closedByPullRequestsReferences"]["nodes"]
        ]
        references = [
            {**item["source"], "relation": "references"}
            for item in issue_node["timelineItems"]["nodes"]
            if (item.get("source") or {}).get("number") is not None
        ]

        candidates = sorted(closes + references, key=lambda pr: 0 if pr["relation"] == "closes" else 1)
        seen: set[int] = set()
        deduped = []
        for pull_request in candidates:
            if pull_request["number"] in seen:
                continue
            seen.add(pull_request["number"])
            deduped.append(pull_request)
        deduped.sort(key=lambda pr: -pr["number"])

        return [
            {
                "number": pr["number"],
                "title": pr["title"],
                "url": pr["url"],
                "state": pr["state"],
                "isDraft": pr["isDraft"],
                "branch": pr["headRefName"],
                "mergedAt": pr["mergedAt"],
                "checks": _checks_state(pr),
                "relation": pr["relation"],
            }
            for pr in deduped
        ]

    def pull_request_files(self, pr_number: str | int) -> list[str]:
        data = run_gh_json(["pr", "view", str(pr_number), *repo_args(), "--json", "files"])
        return [entry["path"] for entry in data.get("files", [])]
