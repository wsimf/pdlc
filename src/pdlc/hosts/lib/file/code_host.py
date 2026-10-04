"""File code host: pull requests come from a `pull_requests.json` under each
record's directory in `$PDLC_HOME`, mirroring the shape the GitHub host returns. `repository` may be omitted and
reads as "" — a file PR belongs to no repository, so its ref is the bare number.
Which of them belong to a record is decided by the explicit registry on the
work item and its tasks (see `internal.pull_requests`), not by this file.

    $PDLC_HOME/records/<n>/pull_requests.json
      [ { "number": 148, "title": "...", "url": "...", "state": "OPEN",
          "isDraft": false, "branch": "feat/x", "mergedAt": null,
          "checks": "PENDING", "headSha": "<optional commit>" } ]
"""

from __future__ import annotations

from pdlc.domain.records import PullRef, PullRequest, ReviewComment

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
            found.extend({"repository": "", **pr} for pr in json.loads(path.read_text(encoding="utf-8")))
    return found


class FileCodeHost(CodeHost):
    def ensure_pull_request_linked(self, code_ref: str) -> PullRequest:
        path = _records_root() / str(code_ref) / "pull_requests.json"
        entries = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        if not entries:
            raise PdlcError(f"no pull request recorded for work item #{code_ref}")
        return {"repository": "", **entries[0]}

    def pull_requests(self, refs: list[PullRef]) -> list[PullRequest]:
        by_ref = {PullRef(int(pr["number"]), pr["repository"]): pr for pr in _all_pull_requests() if pr.get("number") is not None}
        missing = [ref.token() for ref in refs if ref not in by_ref]
        if missing:
            raise PdlcError(f"registered pull requests not found: {missing}")
        return [by_ref[ref] for ref in refs]

    def pull_request_files(self, pr: PullRef) -> list[str]:
        for pull_request in _all_pull_requests():
            if PullRef(int(pull_request.get("number") or 0), pull_request["repository"]) == pr:
                return pull_request.get("files", [])
        return []

    def checkout_task_branch(self, branch: str, pr: int | None, entry_pr: int | None) -> str:
        raise PdlcError("the file code host cannot check out stacked task branches")

    def submit_task_stack(self) -> list[PullRequest]:
        raise PdlcError("the file code host cannot submit stacked pull requests")

    def link_task_stack(self, entry_pr: int, branch: str) -> PullRequest:
        raise PdlcError("the file code host cannot link stacked pull requests")

    def set_pull_request_content(self, pr: PullRef, title: str, body: str) -> None:
        raise PdlcError("the file code host cannot edit pull requests")

    def mark_pull_requests_ready(self, refs: list[PullRef]) -> None:
        # `pull_requests.json` carries no live draft state to transition; a file
        # workflow scenario has nothing to mark ready.
        return None

    def unresolved_review_comments(self, pr: PullRef) -> list[ReviewComment]:
        # `pull_requests.json` carries no live review-thread state either.
        return []
