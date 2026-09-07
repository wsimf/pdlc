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
        """The implementation pull request for the current branch, as a PR dict.
        The caller registers its number on the record; this does not edit the
        PR body or the work item."""

    @abstractmethod
    def pull_requests_by_number(self, numbers: list[int]) -> list[dict]:
        """The given pull requests as dicts, in `numbers` order. Each entry:
        {number, title, url, state, isDraft, branch, mergedAt, checks}. A
        registered number that cannot be resolved must raise; silently dropping
        it would make completion and CI gates unsound. An empty list returns []."""

    @abstractmethod
    def pull_request_files(self, pr_number: str | int) -> list[str]:
        """Repository-relative paths the pull request touches."""

    @abstractmethod
    def submit_task_stack(self) -> list[dict]:
        """Submit the stack the current branch belongs to: sync it, push it, and
        create or update one pull request per branch. Returns every PR in the
        stack bottom-to-top.

        The stack's order, bases, and landed members are the host mechanism's own
        state — callers pass no branch list and PDLC keeps no parallel copy.
        Hosts without a stacked-PR mechanism raise PdlcError."""
