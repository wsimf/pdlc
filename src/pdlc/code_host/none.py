"""Null code host: for a work-item backend with no pull-request linkage
(e.g. the file backend). Every query is empty, so PR-dependent gates report
"not tracked" rather than asserting anything or reaching for a live GitHub.
"""

from __future__ import annotations

from pdlc.code_host.base import CodeHost
from pdlc.pdlc_common import PdlcError


class NoneCodeHost(CodeHost):
    def ensure_pull_request_linked(self, code_ref: str) -> dict:
        raise PdlcError(f"no code host is configured for work item #{code_ref}")

    def pull_requests(self, code_ref: str) -> list[dict]:
        return []

    def pull_request_files(self, pr_number: str | int) -> list[str]:
        return []
