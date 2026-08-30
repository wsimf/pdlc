"""The code-host port: pull requests, their check state, and the files a PR
touched. This is the review/CI side of a PDLC record and stays separate from
`workitem_host` (the record's own state). GitHub is the only implementation
today; the ABC exists so a future GitLab/Bitbucket host is a drop-in.

A `code_ref` is whatever the work item exposes as its code-host linkage — for
the GitHub work-item backend that is the parent Issue number. A backend with
no code linkage passes `None`, and PR-dependent gates report "not tracked"
rather than asserting anything.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class CodeHost(ABC):
    @abstractmethod
    def ensure_pull_request_linked(self, code_ref: str) -> dict:
        """Find the implementation PR for `code_ref` and ensure it closes it."""

    @abstractmethod
    def pull_requests(self, code_ref: str) -> list[dict]:
        """Pull requests attached to `code_ref`, newest first. Each entry:
        {number, title, url, state, isDraft, branch, mergedAt, checks, relation}
        where relation is "closes" or "references". Empty when none."""

    @abstractmethod
    def pull_request_files(self, pr_number: str | int) -> list[str]:
        """Repository-relative paths the pull request touches."""
