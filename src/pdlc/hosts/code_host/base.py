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

from pdlc.domain.records import PullRequest, ReviewComment

from abc import ABC, abstractmethod


class CodeHost(ABC):
    @abstractmethod
    def ensure_pull_request_linked(self, code_ref: str) -> PullRequest:
        """The implementation pull request for the current branch, as a PR dict.
        The caller registers its number on the record; this does not edit the
        PR body or the work item."""

    @abstractmethod
    def pull_requests_by_number(self, numbers: list[int]) -> list[PullRequest]:
        """The given pull requests as dicts, in `numbers` order. Each entry:
        {number, title, url, state, isDraft, branch, mergedAt, checks}. A
        registered number that cannot be resolved must raise; silently dropping
        it would make completion and CI gates unsound. An empty list returns []."""

    @abstractmethod
    def pull_request_files(self, pr_number: str | int) -> list[str]:
        """Repository-relative paths the pull request touches."""

    @abstractmethod
    def task_stack_setup(self, branch: str, entry_pr: int | None) -> list[str]:
        """The lines telling a caller how to put ``branch`` on this host's stack,
        entering at ``entry_pr`` (the previous implemented task's pull request)
        or starting a new stack when it is None.

        Returned as rendered `key: value` lines because the vocabulary is the
        host mechanism's own — PDLC supplies only the branch and the entry point.
        A host with no stacked-PR mechanism returns ``[]`` and the caller
        branches however it likes; it is the read-only counterpart of
        ``submit_task_stack``, which such a host also refuses."""

    @abstractmethod
    def checkout_task_branch(self, branch: str, pr: int | None, entry_pr: int | None) -> str:
        """Put the working tree on ``branch``, creating it on this host's stack
        when it does not exist yet, and return one line saying what was done.

        The three inputs are the three states a delivery task can be in, and the
        host decides which of its own mechanisms each needs: ``pr`` is the task's
        own registered pull request (it has been implemented), ``entry_pr`` the
        previous implemented task's (this task is next on that stack), and
        neither means this is the stack's first task. It is the acting
        counterpart of ``task_stack_setup``, which only describes the same move;
        hosts without a stacked-PR mechanism raise PdlcError, as they do for
        ``submit_task_stack``.

        Callers must have a clean working tree: switching branches with local
        changes is the caller's problem to resolve, not this method's to force."""

    @abstractmethod
    def submit_task_stack(self) -> list[PullRequest]:
        """Submit the stack the current branch belongs to: sync it, push it, and
        create or update one pull request per branch. Returns every PR in the
        stack bottom-to-top.

        The stack's order, bases, and landed members are the host mechanism's own
        state — callers pass no branch list and PDLC keeps no parallel copy.
        Hosts without a stacked-PR mechanism raise PdlcError."""

    @abstractmethod
    def link_task_stack(self, entry_pr: int, branch: str) -> PullRequest:
        """Rename the current branch to ``branch``, publish it, and link it onto
        ``entry_pr``'s stack — the worktree-safe alternative to
        ``task_stack_setup``'s checkout/add for a `pdlc prepare --after`
        worktree's first task, whose predecessor branch may be checked out in
        the predecessor's own, still-active worktree and so cannot be checked
        out here too. Needs no local stack tracking: it pushes the branch and
        creates its pull request itself, chained onto ``entry_pr``.

        Hosts without a stacked-PR mechanism raise PdlcError, matching
        ``submit_task_stack``."""

    @abstractmethod
    def set_pull_request_content(self, number: int, title: str, body: str) -> None:
        """Overwrite one pull request's title and description outright.

        Called at task checkpoint, right after ``submit_task_stack``, so the
        task PR carries the delivery task's own title and its implementation
        evidence rather than the stack mechanism's auto-generated summary. A
        host with no stacked-PR mechanism raises PdlcError, matching
        ``submit_task_stack``; the checkpoint path never reaches it there."""

    @abstractmethod
    def unresolved_review_comments(self, pr_number: str | int) -> list[ReviewComment]:
        """Every review-thread comment on this pull request that is still
        unresolved on the host, oldest first: one entry per thread — its root
        comment only, not later replies — as
        {author, body, url, path, line}. A host with no review-thread concept
        (or no live review state, e.g. a local file record) returns []; this
        is a review-feedback signal, not a registry, so it never raises for
        "none found"."""

    @abstractmethod
    def mark_pull_requests_ready(self, numbers: list[int]) -> None:
        """Take the given pull requests out of draft so humans can review them.

        Called once at ``pdlc post implement`` — after every delivery task is
        closed and the record enters phase review — for every open PR registered
        on the record and its tasks, which in the stacked flow is more than one.
        Must be idempotent: an already-ready PR is left untouched, so a
        ``Changes Required`` bounce that republishes is safe. A host with no
        draft concept does nothing; a merged or closed number is skipped by the
        caller, not raised on here."""
