"""File code host: pull requests come from a `pull_requests.json` under each
record's directory in `$PDLC_HOME`, mirroring the shape the GitHub host returns.
Which of them belong to a record is decided by the explicit registry on the
work item and its tasks (see `internal.pull_requests`), not by this file.

    $PDLC_HOME/records/<n>/pull_requests.json
      [ { "number": 148, "title": "...", "url": "...", "state": "OPEN",
          "isDraft": false, "branch": "feat/x", "mergedAt": null,
          "checks": "PENDING" } ]
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pdlc.hosts.code_host.base import CodeHost
from pdlc.domain.lifecycle import PdlcError


def _records_root() -> Path:
    return Path(os.environ.get("PDLC_HOME", ".pdlc")) / "records"


def _all_pull_requests() -> list[dict]:
    found: list[dict] = []
    root = _records_root()
    if not root.is_dir():
        return found
    for record in root.glob("*"):
        path = record / "pull_requests.json"
        if path.is_file():
            found.extend(json.loads(path.read_text()))
    return found


class FileCodeHost(CodeHost):
    def ensure_pull_request_linked(self, code_ref: str) -> dict:
        path = _records_root() / str(code_ref) / "pull_requests.json"
        entries = json.loads(path.read_text()) if path.is_file() else []
        if not entries:
            raise PdlcError(f"no pull request recorded for work item #{code_ref}")
        return entries[0]

    def pull_requests_by_number(self, numbers: list[int]) -> list[dict]:
        wanted = [int(n) for n in numbers]
        by_number = {int(pr["number"]): pr for pr in _all_pull_requests() if pr.get("number") is not None}
        return [by_number[n] for n in wanted if n in by_number]

    def pull_request_files(self, pr_number: str | int) -> list[str]:
        for pull_request in _all_pull_requests():
            if str(pull_request.get("number")) == str(pr_number):
                return pull_request.get("files", [])
        return []

    def submit_task_stack(self) -> list[dict]:
        raise PdlcError("the file code host cannot submit stacked pull requests")
