"""Null code host: for a work-item backend with no pull-request linkage
(e.g. the file backend). Every query is empty, so PR-dependent gates report
"not tracked" rather than asserting anything or reaching for a live GitHub.
"""

from __future__ import annotations

from pdlc.hosts.code_host.base import CodeHost
from pdlc.domain.lifecycle import PdlcError


class NoneCodeHost(CodeHost):
    def ensure_pull_request_linked(self, code_ref: str) -> dict:
        raise PdlcError(f"no code host is configured for work item #{code_ref}")

    def pull_requests_by_number(self, numbers: list[int]) -> list[dict]:
        return []

    def pull_request_files(self, pr_number: str | int) -> list[str]:
        return []

    def submit_task_stack(self) -> list[dict]:
        raise PdlcError("no code host is configured; cannot submit a stacked pull request")
