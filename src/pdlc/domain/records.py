"""Normalized values exchanged between workflow services and host adapters."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict, cast

from pdlc.domain.lifecycle import PdlcError


_PULL_REF = re.compile(r"\A(?:([\w.-]+/[\w.-]+)#|#)?(\d+)\Z")


@dataclass(frozen=True, order=True)
class PullRef:
    """One registered pull request: its number and the `owner/name` code
    repository holding it, casefolded. ``repository`` is "" for a code
    provider without repositories (the file and none hosts), so a
    single-repository registry still reads as plain numbers.

    Ordered by number first, so ``max(refs)`` is a task's latest PR."""

    number: int
    repository: str = ""

    @classmethod
    def parse(cls, text: str, default_repository: str) -> PullRef:
        """``N``, ``#N``, or ``owner/name#N``; a bare number belongs to
        ``default_repository``. Raises PdlcError on anything else."""
        match = _PULL_REF.match(text.strip())
        if not match or int(match.group(2)) < 1:
            raise PdlcError(f"pull request must be N or owner/name#N: {text!r}")
        return cls(int(match.group(2)), (match.group(1) or default_repository).casefold())

    def token(self) -> str:
        """The registry form: ``owner/name#N``, or ``N`` without a repository."""
        return f"{self.repository}#{self.number}" if self.repository else str(self.number)

    def label(self, default_repository: str) -> str:
        """The display form: ``#N`` in ``default_repository``, else ``owner/name#N``."""
        return f"#{self.number}" if self.repository in ("", default_repository) else self.token()

    def json(self, default_repository: str) -> int | str:
        """The command-output form: the bare number in ``default_repository``,
        so single-repository output stays numeric, else ``owner/name#N``."""
        return self.number if self.repository in ("", default_repository) else self.token()


def parse_pull_refs(tokens: Iterable[object], default_repository: str) -> list[PullRef]:
    """Stored registry tokens as sorted, de-duplicated refs. Integers and
    unparseable tokens are tolerated — registries can be hand-edited — the
    former read as ``default_repository``'s, the latter dropped."""
    refs: set[PullRef] = set()
    for token in tokens:
        if type(token) is int and token > 0:
            refs.add(PullRef(token, default_repository))
        elif isinstance(token, str):
            try:
                refs.add(PullRef.parse(token, default_repository))
            except PdlcError:
                continue
    return sorted(refs)


def pull_request_label(pr: dict[str, Any]) -> str:
    """A PR dict's display name: its stamped `label`, else `#N`."""
    return pr.get("label") or f"#{pr['number']}"


def pull_ref(pr: PullRequest) -> PullRef:
    """The registry identity of a resolved pull request."""
    return PullRef(pr["number"], pr["repository"])


class RecordContent(TypedDict):
    number: int
    title: str
    url: str


class Author(TypedDict):
    login: str


class Comment(TypedDict):
    body: str
    createdAt: str
    url: str
    author: Author


QueueItemSummary = TypedDict("QueueItemSummary", {
    "id": str, "content": RecordContent, "Status": str, "Gate State": str,
    "Lifecycle": str, "Skipped States": str, "workType": str,
})

WorkItem = TypedDict("WorkItem", {
    "id": str, "content": RecordContent, "Status": str, "Gate State": str,
    "Lifecycle": str, "Skipped States": str, "workType": str,
    "Slug": str, "issueBody": str, "prs": list[PullRef],
    "number": NotRequired[int], "comments": NotRequired[list[Comment]],
})


class Task(TypedDict):
    number: int
    title: str
    url: str
    state: Literal["OPEN", "CLOSED"]
    body: str
    comments: list[str]
    taskId: str | None
    prs: list[PullRef]
    commentObjects: NotRequired[list[Comment]]
    commentsMeta: NotRequired[dict[str, Any]]
    hasPlan: NotRequired[bool]
    hasImplementation: NotRequired[bool]
    implementationInvalidated: NotRequired[bool]
    planComment: NotRequired[str | None]
    planCommentUrl: NotRequired[str | None]
    needsPlan: NotRequired[bool]
    isUI: NotRequired[bool]


class TaskInput(TypedDict):
    id: str
    title: str
    bodyText: str


class TaskPublication(TypedDict):
    action: Literal["created", "updated", "retitled", "unchanged"]
    taskId: str
    number: int
    title: str
    url: str


class CreatedRecord(TypedDict):
    id: str
    number: int
    url: str


class CheckResult(TypedDict):
    """One CI check on a pull request's head commit, as `pdlc inspect checks`
    lists it. `state` is the host's own vocabulary (`SUCCESS`, `FAILURE`,
    `PENDING`, ...); `ignored` marks a check matching `[code.github]
    ignored_checks`, which the PR's `checks` rollup already leaves out."""
    name: str
    state: str
    url: str
    ignored: bool


class PullRequest(TypedDict):
    number: int
    # Casefolded `owner/name` holding the PR; "" for a code provider without
    # repositories. With `number` it forms the PR's `PullRef`.
    repository: str
    title: str
    url: str
    state: Literal["OPEN", "CLOSED", "MERGED"]
    isDraft: bool
    branch: str
    mergedAt: str | None
    checks: str
    # The head commit the host last saw; lets a merged PR's local branch be
    # deleted only when it holds nothing the PR did not. Empty or absent when
    # the host does not report it.
    headSha: NotRequired[str]
    files: NotRequired[list[str]]
    # How output names the PR (`#N`, or `owner/name#N` outside the configured
    # code repository); stamped by `internal.pull_requests.record_pull_requests`.
    label: NotRequired[str]


class ReviewComment(TypedDict):
    author: str
    body: str
    url: str | None
    path: str | None
    line: int | None


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PdlcError(f"{label} must be an object")
    return value


def _strings(value: dict[str, Any], names: tuple[str, ...], label: str) -> None:
    for name in names:
        if not isinstance(value.get(name), str):
            raise PdlcError(f"{label}.{name} must be a string")


def _refs(value: object, label: str) -> None:
    if not isinstance(value, list) or any(not isinstance(ref, PullRef) for ref in value):
        raise PdlcError(f"{label} must be an array of pull request refs")


def validate_work_item(value: object) -> WorkItem:
    item = _object(value, "work item")
    _strings(item, ("id", "issueBody", "Status", "Gate State", "Lifecycle", "Skipped States", "Slug", "workType"), "work item")
    content = _object(item.get("content"), "work item.content")
    _strings(content, ("title", "url"), "work item.content")
    if type(content.get("number")) is not int or content["number"] < 1:
        raise PdlcError("work item.content.number must be a positive integer")
    _refs(item.get("prs"), "work item.prs")
    return cast(WorkItem, item)


def validate_task(value: object) -> Task:
    task = _object(value, "task")
    _strings(task, ("title", "url", "body"), "task")
    if type(task.get("number")) is not int or task["number"] < 1:
        raise PdlcError("task.number must be a positive integer")
    if task.get("state") not in ("OPEN", "CLOSED"):
        raise PdlcError("task.state must be OPEN or CLOSED")
    if not isinstance(task.get("comments"), list) or any(not isinstance(c, str) for c in task["comments"]):
        raise PdlcError("task.comments must be an array of strings")
    objects = task.get("commentObjects")
    if objects is not None and (not isinstance(objects, list) or any(not isinstance(c, dict) or not isinstance(c.get("body"), str) for c in objects)):
        raise PdlcError("task.commentObjects must be an array of comment objects")
    if task.get("taskId") is not None and not isinstance(task["taskId"], str):
        raise PdlcError("task.taskId must be a string or null")
    _refs(task.get("prs"), "task.prs")
    return cast(Task, task)


def validate_task_inputs(values: list[dict[str, Any]]) -> list[TaskInput]:
    result: list[TaskInput] = []
    for value in values:
        _strings(value, ("id", "title", "bodyText"), "task input")
        result.append({"id": value["id"], "title": value["title"], "bodyText": value["bodyText"]})
    return result


def validate_pull_request(value: object) -> PullRequest:
    pr = _object(value, "pull request")
    _strings(pr, ("repository", "title", "url", "branch", "checks"), "pull request")
    if type(pr.get("number")) is not int or pr["number"] < 1:
        raise PdlcError("pull request.number must be a positive integer")
    if pr.get("state") not in ("OPEN", "CLOSED", "MERGED"):
        raise PdlcError("pull request.state must be OPEN, CLOSED, or MERGED")
    if not isinstance(pr.get("isDraft"), bool):
        raise PdlcError("pull request.isDraft must be a boolean")
    if pr.get("mergedAt") is not None and not isinstance(pr["mergedAt"], str):
        raise PdlcError("pull request.mergedAt must be a string or null")
    return cast(PullRequest, pr)
