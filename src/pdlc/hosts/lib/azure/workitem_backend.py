"""Azure DevOps Boards work-item backend: the PDLC record is a work item of
the configured record type (`Product Backlog Item` on the Scrum process), its
state is a set of custom fields on that work item, and its delivery tasks are
child work items of type `Task`.

Paired with the GitHub code host — Azure Boards for planning, GitHub repos for
code — so pull requests are GitHub numbers stored in `Custom.PdlcPrs` rather
than Azure `ArtifactLink` relations, which can only address Azure Repos.

The custom fields are an org-admin precondition (see "Azure Boards fields" in
README.md); this backend never creates or probes them.
"""

from __future__ import annotations

from pdlc.domain.records import Comment, CreatedRecord, QueueItemSummary, Task, TaskInput, TaskPublication, WorkItem

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, TypeVar

import pdlc.hosts.lib.azure.workitems as azure
from pdlc.config import get_config
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import TASK_ID_PATTERN, TASK_TITLE_PATTERN
from pdlc.domain.workflow import WorkType
from pdlc.hosts.lib.azure.transport import run_az
from pdlc.hosts.workitem_host.base import CommentPage, WorkItemBackend

DEFAULT_RECORD_TYPE = "Product Backlog Item"
DEFAULT_CLOSED_STATE = "Done"
DEFAULT_OPEN_STATE = "To Do"

# A delivery task's comments have no batch API, so a record with N tasks needs
# N reads, each paying `az devops invoke`'s ~1.3s of resource discovery. Every
# call is its own subprocess, so threads make them genuinely concurrent; the
# bound keeps a large record from starting one process per task at once.
_MAX_PARALLEL_READS = 8

T = TypeVar("T")
R = TypeVar("R")

# `Removed` is Azure's "this was abandoned" terminal state and `Closed` is the
# Agile template's terminal state; PDLC only cares that such a task no longer
# blocks a transition, regardless of which state `close_task` writes.
_ALWAYS_CLOSED_STATES = {"Removed", "Closed"}


def _record_type() -> str:
    return get_config().azure_record_type or DEFAULT_RECORD_TYPE


def _area_path() -> str | None:
    """The optional `[backend.azure] area_path` new records are filed under."""
    return get_config().azure_area_path


def _closed_state() -> str:
    return get_config().azure_closed_state or DEFAULT_CLOSED_STATE


def _open_state() -> str:
    return get_config().azure_open_state or DEFAULT_OPEN_STATE


# Delivery tasks (`Task`) commonly use a different state vocabulary than the
# record's own work-item type; an unset task override falls back to the
# work-item state name.
def _task_closed_state() -> str:
    return get_config().azure_task_closed_state or _closed_state()


def _task_open_state() -> str:
    return get_config().azure_task_open_state or _open_state()


def _task_in_progress_state() -> str | None:
    return get_config().azure_task_in_progress_state


def _assigned_to() -> str | None:
    """The optional `[backend.azure] assigned_to` queue-scan filter."""
    return get_config().azure_assigned_to


def _assignee() -> str:
    """Who a newly created record or task is assigned to: the configured
    `assigned_to` identity, or the signed-in account if that is unset or the
    `@me` macro — `@me` only resolves in a WIQL filter, not a field write."""
    configured = (_assigned_to() or "").strip()
    if configured and configured.casefold() != "@me":
        return configured
    return run_az(["account", "show", "--query", "user.name", "-o", "tsv"]).strip()


def _gather(read: Callable[[T], R], items: Iterable[T]) -> list[R]:
    """Run one read per item concurrently, preserving order. The first failure
    is re-raised, so a partial result never reaches a caller."""
    items = list(items)
    if len(items) < 2:
        return [read(item) for item in items]
    with ThreadPoolExecutor(max_workers=min(_MAX_PARALLEL_READS, len(items))) as pool:
        return list(pool.map(read, items))


def _text(fields: dict, name: str) -> str:
    value = fields.get(name)
    return "" if value is None else str(value)


def _parse_prs(fields: dict) -> list[int]:
    """`Custom.PdlcPrs` as a sorted number list. Unparseable tokens are dropped
    rather than failing a read — the field is human-editable in the Azure UI."""
    return sorted({int(token) for token in _text(fields, azure.PRS_FIELD).split() if token.isdigit()})


def _work_type(fields: dict) -> str:
    """The work-item type as a PDLC work type. The configured record type is
    the Feature pipeline whatever it is named; anything else keeps its own
    lower-cased name so an unknown type is blocked rather than guessed."""
    name = _text(fields, azure.TYPE_FIELD)
    if name.casefold() == _record_type().casefold():
        return WorkType.FEATURE.value
    return name.strip().lower()


def _comment_view(comment: dict) -> Comment:
    return {
        "body": comment.get("text") or "",
        "createdAt": comment.get("createdDate") or "",
        "url": comment.get("url") or "",
        "author": {"login": (comment.get("createdBy") or {}).get("uniqueName") or ""},
    }


class AzureWorkItemBackend(WorkItemBackend):
    capabilities = {"subissue_graph", "queue_scan"}

    # --- resolution ---

    def _item(self, ref: str) -> dict:
        ref = str(ref)
        return azure.show(ref) if ref.isdigit() else azure.by_slug(ref, _record_type())

    def _record_id(self, ref: str) -> int:
        return int(self._item(ref)["id"])

    def _record_view(self, item: dict) -> dict:
        fields = item.get("fields") or {}
        number = int(item["id"])
        return {
            "id": str(number),
            "number": number,
            "content": {
                "number": number,
                "title": _text(fields, azure.TITLE_FIELD),
                "url": azure.item_url(number),
            },
            "issueBody": _text(fields, azure.DESCRIPTION_FIELD),
            "prs": _parse_prs(fields),
            "Status": _text(fields, azure.STATUS_FIELD),
            "Gate State": _text(fields, azure.GATE_FIELD),
            "Lifecycle": _text(fields, azure.LIFECYCLE_FIELD),
            "Skipped States": _text(fields, azure.SKIPPED_FIELD),
            "Slug": _text(fields, azure.SLUG_FIELD),
            "workType": _work_type(fields),
        }

    def resolve(self, ref: str) -> WorkItem:
        return self._record_view(self._item(ref))

    def queue_items(self) -> list[QueueItemSummary]:
        summaries: list[QueueItemSummary] = []
        for item in azure.records(_record_type(), _assigned_to()):
            fields = item.get("fields") or {}
            number = int(item["id"])
            summaries.append({
                "id": str(number),
                "content": {
                    "number": number,
                    "title": _text(fields, azure.TITLE_FIELD),
                    "url": azure.item_url(number),
                },
                "Status": _text(fields, azure.STATUS_FIELD),
                "Gate State": _text(fields, azure.GATE_FIELD),
                "Lifecycle": _text(fields, azure.LIFECYCLE_FIELD),
                "Skipped States": _text(fields, azure.SKIPPED_FIELD),
                "workType": _work_type(fields),
            })
        return summaries

    # --- state fields ---

    # `item_id` is the work item's own id, so every field write is one PATCH
    # against it — no separate item/board handle the way GitHub Projects needs.

    def set_state(self, item_id: str, status: str, gate: str, lifecycle: str) -> None:
        azure.update(item_id, {
            azure.STATUS_FIELD: status,
            azure.GATE_FIELD: gate,
            azure.LIFECYCLE_FIELD: lifecycle,
        })

    def set_gate(self, item_id: str, gate: str) -> None:
        azure.update(item_id, {azure.GATE_FIELD: gate})

    def set_slug(self, item_id: str, value: str) -> None:
        azure.update(item_id, {azure.SLUG_FIELD: value})

    def set_skipped_states(self, item_id: str, value: str) -> None:
        azure.update(item_id, {azure.SKIPPED_FIELD: value})

    def close_record(self, ref: str) -> None:
        azure.update(self._record_id(ref), state=_closed_state())

    # --- body ---

    def write_body(self, ref: str, body: str) -> None:
        # Nothing to preserve: attached pull requests live in their own field,
        # so the description is human-authored content end to end.
        azure.update(self._record_id(ref), {azure.DESCRIPTION_FIELD: body})

    # --- comments ---

    def comments(self, ref: str) -> list[Comment]:
        return [_comment_view(comment) for comment in azure.comments(azure.numeric(ref))]

    def comments_page(self, ref: str, page: int = 1, per_page: int = 100) -> CommentPage:
        result = azure.comments_page(azure.numeric(ref), page, per_page)
        comments = [_comment_view(comment) for comment in result.get("comments") or []]
        total = int(result.get("totalCount") or 0)
        return CommentPage(comments, page, per_page, total, bool(result.get("continuationToken")))

    def post_comment(self, ref: str, body: str) -> str:
        return azure.post_comment(azure.numeric(ref), body)

    def edit_comment(self, ref: str, comment_ref: str, body: str) -> str:
        return azure.edit_comment(azure.numeric(ref), comment_ref, body)

    def delete_comment(self, ref: str, comment_ref: str) -> None:
        azure.delete_comment(azure.numeric(ref), comment_ref)

    def post_blocker(self, ref: str, body: str) -> str:
        # Same channel as an ordinary comment, matching GitHub: the
        # `Decision Required` gate is the machine signal and the PDLC-DECISION
        # marker the human one. A `pdlc-blocked` tag would add a second place
        # to keep in sync for no reader that needs it yet.
        return self.post_comment(ref, body)

    # --- delivery tasks ---

    # `_task_view` does no I/O: its comments are fetched by `_task_views` so a
    # whole record's worth can go out at once.
    def _task_view(self, item: dict, comments: list[dict]) -> dict:
        fields = item.get("fields") or {}
        number = int(item["id"])
        title = _text(fields, azure.TITLE_FIELD)
        state = _text(fields, azure.STATE_FIELD)
        match = TASK_ID_PATTERN.match(title)
        return {
            "number": number,
            "title": title,
            "url": azure.item_url(number),
            "state": "CLOSED" if state in {_task_closed_state(), *_ALWAYS_CLOSED_STATES} else "OPEN",
            "body": _text(fields, azure.DESCRIPTION_FIELD),
            "comments": [comment.get("text") or "" for comment in comments],
            "commentObjects": [_comment_view(comment) for comment in comments],
            "taskId": match.group(1) if match else None,
            "prs": _parse_prs(fields),
        }

    def _task_views(self, items: list[dict]) -> list[dict]:
        comments = _gather(azure.comments, [int(item["id"]) for item in items])
        return [self._task_view(item, batch) for item, batch in zip(items, comments)]

    def tasks(self, ref: str) -> list[Task]:
        return self._task_views(azure.children(self._record_id(ref)))

    def tasks_by_number(self, numbers: list[str]) -> list[Task]:
        return self._task_views(_gather(azure.show, [azure.numeric(number) for number in numbers]))

    def upsert_tasks(self, parent: str, tasks: list[TaskInput], existing: list[Task]) -> list[TaskPublication]:
        record = self._item(parent)
        parent_id = int(record["id"])
        # A new task lands in its parent's area path.
        parent_area = _text(record.get("fields") or {}, azure.AREA_PATH_FIELD)
        by_id = {task["taskId"]: task for task in existing if task.get("taskId")}
        return [
            self._upsert(parent_id, parent_area, task, by_id.get(task["id"]))
            for task in tasks
        ]

    def _upsert(self, parent_id: int, parent_area: str, task: dict, match: dict | None) -> dict:
        """Create or update one delivery task, matched by its stable
        WORK-NNN-TASK-NNN identity rather than its wording, so a reworded task
        is still the same task."""
        task_id = task["id"]
        full_title = f"WORK-{parent_id}-{task_id} {task['title']}"
        body_text = task["bodyText"]

        recovered = False
        if match is None:
            candidates = [
                item for item in azure.tasks_with_identity(parent_id, task_id)
                if (identity := TASK_TITLE_PATTERN.match(_text(item.get("fields") or {}, azure.TITLE_FIELD)))
                and identity.group(1) == str(parent_id) and identity.group(2) == task_id
            ]
            if len(candidates) > 1:
                raise PdlcError(f"multiple Azure tasks carry stable identity WORK-{parent_id}-{task_id}")
            if candidates:
                candidate = candidates[0]
                existing_parent = (candidate.get("fields") or {}).get(azure.PARENT_FIELD)
                if existing_parent and int(existing_parent) != parent_id:
                    raise PdlcError(f"task {candidate['id']} belongs to another parent")
                match = self._task_view(candidate, [])
                recovered = not existing_parent

        if match:
            number = match["number"]
            title_changed = match.get("title") != full_title
            body_changed = (match.get("body") or "") != body_text
            if title_changed or body_changed:
                azure.update(number, {
                    azure.TITLE_FIELD: full_title,
                    azure.DESCRIPTION_FIELD: body_text,
                })
                action = "retitled" if title_changed else "updated"
            else:
                action = "unchanged"
        else:
            fields = {
                azure.DESCRIPTION_FIELD: body_text,
                azure.ASSIGNED_TO_FIELD: _assignee(),
            }
            if parent_area:
                fields[azure.AREA_PATH_FIELD] = parent_area
            created = azure.create(azure.TASK_TYPE, full_title, fields)
            number = int(created["id"])
            azure.add_parent(number, parent_id)
            action = "created"

        if recovered:
            azure.add_parent(number, parent_id)

        return {
            "action": action, "taskId": task_id, "number": number,
            "title": full_title, "url": azure.item_url(number),
        }

    def close_task(self, task_ref: str) -> None:
        azure.update(azure.numeric(task_ref), state=_task_closed_state())

    def remove_task(self, parent: str, task_ref: str) -> None:
        child_id = azure.numeric(task_ref)
        azure.update(child_id, state=_task_closed_state())
        azure.remove_parent(child_id, self._record_id(parent))

    def reopen_task(self, task_ref: str) -> None:
        azure.update(azure.numeric(task_ref), state=_task_open_state())

    def task_pr_numbers(self, ref: str) -> list[int]:
        items = azure.children(self._record_id(ref), ("System.Id", azure.PRS_FIELD))
        return sorted({number for item in items for number in _parse_prs(item.get("fields") or {})})

    # --- attached pull requests ---

    # Records and delivery tasks both carry `Custom.PdlcPrs`, so one
    # implementation serves each and the description stays human content.

    def attach_pr(self, ref: str, pr_number: int) -> list[int]:
        item = azure.show(azure.numeric(ref))
        current = _parse_prs(item.get("fields") or {})
        numbers = sorted({*current, int(pr_number)})
        if numbers != current:
            azure.update(item["id"], {azure.PRS_FIELD: " ".join(str(number) for number in numbers)})
        return numbers

    def attached_prs(self, ref: str) -> list[int]:
        return _parse_prs(azure.show(azure.numeric(ref)).get("fields") or {})

    # --- creation ---

    def create(self, title: str, body: str, slug: str, work_type: WorkType = WorkType.FEATURE) -> CreatedRecord:
        work_type = self._validated_work_type(work_type)
        if work_type is not WorkType.FEATURE:
            raise PdlcError(f"Azure creation is unavailable for work type: {work_type.value}")
        # Every field lands in the create call, and a work item is on its board
        # the moment it exists — no equivalent of GitHub's `project item-add`.
        fields = {
            azure.DESCRIPTION_FIELD: body,
            azure.SLUG_FIELD: slug,
            azure.ASSIGNED_TO_FIELD: _assignee(),
        }
        if area := _area_path():
            fields[azure.AREA_PATH_FIELD] = area
        item = azure.create(_record_type(), title, fields)
        number = int(item["id"])
        return {"id": str(number), "number": number, "url": azure.item_url(number)}

    # --- identity ---

    def current_actor(self) -> str:
        return run_az(["account", "show", "--query", "user.name", "-o", "tsv"]).strip()

    def ref_label(self) -> str:
        return get_config().azure_project or "pdlc"
