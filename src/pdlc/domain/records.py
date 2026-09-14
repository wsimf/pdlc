"""Normalized values exchanged between workflow services and host adapters."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict, cast

from pdlc.domain.lifecycle import PdlcError


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
    "Slug": str, "issueBody": str, "prs": list[int],
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
    prs: list[int]
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


class PullRequest(TypedDict):
    number: int
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


def _numbers(value: object, label: str) -> None:
    if not isinstance(value, list) or any(type(n) is not int or n < 1 for n in value):
        raise PdlcError(f"{label} must be an array of positive integers")


def validate_work_item(value: object) -> WorkItem:
    item = _object(value, "work item")
    _strings(item, ("id", "issueBody", "Status", "Gate State", "Lifecycle", "Skipped States", "Slug", "workType"), "work item")
    content = _object(item.get("content"), "work item.content")
    _strings(content, ("title", "url"), "work item.content")
    if type(content.get("number")) is not int or content["number"] < 1:
        raise PdlcError("work item.content.number must be a positive integer")
    _numbers(item.get("prs"), "work item.prs")
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
    _numbers(task.get("prs"), "task.prs")
    return cast(Task, task)


def validate_task_inputs(values: list[dict[str, Any]]) -> list[TaskInput]:
    result: list[TaskInput] = []
    for value in values:
        _strings(value, ("id", "title", "bodyText"), "task input")
        result.append({"id": value["id"], "title": value["title"], "bodyText": value["bodyText"]})
    return result


def validate_pull_request(value: object) -> PullRequest:
    pr = _object(value, "pull request")
    _strings(pr, ("title", "url", "branch", "checks"), "pull request")
    if type(pr.get("number")) is not int or pr["number"] < 1:
        raise PdlcError("pull request.number must be a positive integer")
    if pr.get("state") not in ("OPEN", "CLOSED", "MERGED"):
        raise PdlcError("pull request.state must be OPEN, CLOSED, or MERGED")
    if not isinstance(pr.get("isDraft"), bool):
        raise PdlcError("pull request.isDraft must be a boolean")
    if pr.get("mergedAt") is not None and not isinstance(pr["mergedAt"], str):
        raise PdlcError("pull request.mergedAt must be a string or null")
    return cast(PullRequest, pr)
