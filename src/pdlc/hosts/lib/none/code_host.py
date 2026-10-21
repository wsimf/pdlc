"""Null code host: for a work-item backend with no pull-request linkage
(e.g. the file backend). Every query is empty, so PR-dependent gates report
"not tracked" rather than asserting anything or reaching for a live GitHub.
"""

from __future__ import annotations

from pdlc.domain.records import CheckResult, PullRef, PullRequest, ReviewComment

from pdlc.hosts.code_host.base import CodeHost
from pdlc.domain.lifecycle import PdlcError


class NoneCodeHost(CodeHost):
    def ensure_pull_request_linked(self, code_ref: str) -> PullRequest:
        raise PdlcError(f"no code host is configured for work item #{code_ref}")

    def pull_requests(self, refs: list[PullRef]) -> list[PullRequest]:
        if refs:
            raise PdlcError("registered pull requests cannot be resolved without a code host")
        return []

    def pull_request_files(self, pr: PullRef) -> list[str]:
        return []

    def pull_request_checks(self, pr: PullRef) -> list[CheckResult]:
        return []

    def checkout_task_branch(self, branch: str, pr: int | None, entry_pr: int | None) -> str:
        raise PdlcError("no code host is configured; cannot check out a stacked task branch")

    def submit_task_stack(self) -> list[PullRequest]:
        raise PdlcError("no code host is configured; cannot submit a stacked pull request")

    def link_task_stack(self, entry_pr: int, branch: str) -> PullRequest:
        raise PdlcError("no code host is configured; cannot link a stacked pull request")

    def set_pull_request_content(self, pr: PullRef, title: str, body: str) -> None:
        raise PdlcError("no code host is configured; cannot edit a pull request")

    def mark_pull_requests_ready(self, refs: list[PullRef]) -> None:
        if refs:
            raise PdlcError("no code host is configured; cannot mark a pull request ready")

    def unresolved_review_comments(self, pr: PullRef) -> list[ReviewComment]:
        return []
