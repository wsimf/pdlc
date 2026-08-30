"""File code host: pull requests for a record come from an optional
`pull_requests.json` in that record's directory under `$PDLC_HOME`, mirroring
what `code_host.github` returns from GitHub. Absent that file, the record has
no linked PRs — the same "not tracked" answer the null host gives.

    $PDLC_HOME/records/<n>/pull_requests.json
      [ { "number": 148, "title": "...", "url": "...", "state": "OPEN",
          "isDraft": false, "branch": "feat/x", "mergedAt": null,
          "checks": "PENDING", "relation": "closes" } ]
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from code_host.base import CodeHost
from pdlc_common import PdlcError


def _record_dir(ref: str) -> Path:
    return Path(os.environ.get("PDLC_HOME", ".pdlc")) / "records" / str(ref)


class FileCodeHost(CodeHost):
    def ensure_pull_request_linked(self, code_ref: str) -> dict:
        pull_requests = self.pull_requests(code_ref)
        linked = next((pr for pr in pull_requests if pr.get("relation") == "closes"), None)
        if not linked:
            raise PdlcError(f"no pull request linked to work item #{code_ref}")
        return linked

    def pull_requests(self, code_ref: str) -> list[dict]:
        path = _record_dir(code_ref) / "pull_requests.json"
        if not path.is_file():
            return []
        return json.loads(path.read_text())

    def pull_request_files(self, pr_number: str | int) -> list[str]:
        for record in (Path(os.environ.get("PDLC_HOME", ".pdlc")) / "records").glob("*"):
            path = record / "pull_requests.json"
            if not path.is_file():
                continue
            for pull_request in json.loads(path.read_text()):
                if str(pull_request.get("number")) == str(pr_number):
                    return pull_request.get("files", [])
        return []
