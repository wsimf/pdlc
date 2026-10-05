"""File work-item backend: a PDLC record is a directory under `$PDLC_HOME`
(default `.pdlc`), its state is a JSON file, its body is `body.md`, its
evidence is an append-only `comments.jsonl`, and its delivery tasks are
child directories under `tasks/`.

    $PDLC_HOME/
      seq                        shared monotonic counter (records + tasks)
      records/<n>/
        meta.json                {id, number, title, url, fields:{...}, prs:[…], state?}
        body.md
        comments.jsonl
        tasks/<m>/
          meta.json              {number, title, url, state, taskId, prs:[…]}
          body.md
          comments.jsonl

The store mirrors GitHub closely enough that the `pdlc-*` scripts and the
`workitem` facade cannot tell the two apart: records and tasks share one
number space, tasks keep a stable `WORK-<n>-TASK-NNN` identity, and comments
are append-only except for `edit_comment`, which rewrites one entry in place,
and `delete_comment`, which removes it outright — both addressed by a
comment's own `#comment-N` `url`, where `N` is a monotonic id (`meta.json`'s
`commentSeq`) that is never reused, not the comment's current position, so a
reference stays valid even after an earlier comment is deleted.
"""

from __future__ import annotations

from pdlc.domain.records import Comment, CreatedRecord, PullRef, QueueItemSummary, Task, TaskInput, TaskPublication, WorkItem, parse_pull_refs

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pdlc.config import get_config
from pdlc.domain.lifecycle import NotFound, PdlcError
from pdlc.domain.task_artifact import same_task_body
from pdlc.domain.workflow import WorkType
from pdlc.hosts.lib.file.storage import atomic_write, single_writer
from pdlc.hosts.workitem_host.base import CommentPage, WorkItemBackend

FIELD_NAMES = ("Status", "Gate State", "Lifecycle", "Skipped States", "Slug")


def _home() -> Path:
    root = Path(os.environ.get("PDLC_HOME", ".pdlc"))
    return root


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FileWorkItemBackend(WorkItemBackend):
    capabilities = {"subissue_graph", "queue_scan"}

    # --- number allocation ---

    def _next_number(self) -> int:
        seq = _home() / "seq"
        (_home() / "records").mkdir(parents=True, exist_ok=True)
        current = int(seq.read_text(encoding="utf-8")) if seq.exists() else 0
        current += 1
        atomic_write(seq, str(current))
        return current

    # --- record directories ---

    def _record_dir(self, ref: str) -> Path:
        records = _home() / "records"
        ref = str(ref)
        if ref.isdigit():
            path = records / ref
            if not path.is_dir():
                raise NotFound(f"no PDLC record for #{ref}")
            return path
        if not records.is_dir():
            raise NotFound(f"no PDLC record with slug: {ref}")
        matches = [
            child for child in records.iterdir()
            if child.is_dir() and _read_meta(child).get("fields", {}).get("Slug") == ref
        ]
        if not matches:
            raise NotFound(f"no PDLC record with slug: {ref}")
        if len(matches) > 1:
            raise PdlcError(f"slug is ambiguous: {ref}")
        return matches[0]

    def _task_dir(self, number: str) -> Path:
        number = str(number)
        records = _home() / "records"
        if not records.is_dir():
            raise NotFound(f"no delivery task for #{number}")
        for record in records.iterdir():
            candidate = record / "tasks" / number
            if candidate.is_dir():
                return candidate
        raise NotFound(f"no delivery task for #{number}")

    # A comment target is a record or one of its delivery tasks — both are
    # addressed by their shared number, the same way GitHub Issues are.
    def _entity_dir(self, ref: str) -> Path:
        ref = str(ref)
        if ref.isdigit():
            record = _home() / "records" / ref
            if record.is_dir():
                return record
            return self._task_dir(ref)
        return self._record_dir(ref)

    # --- assembly ---

    def _record_view(self, path: Path) -> dict:
        meta = _read_meta(path)
        fields = meta.get("fields", {})
        body = (path / "body.md").read_text(encoding="utf-8") if (path / "body.md").exists() else ""
        return {
            "id": meta["id"],
            "number": meta["number"],
            "content": {"number": meta["number"], "title": meta.get("title"), "url": meta.get("url")},
            "issueBody": body,
            "prs": _prs(meta),
            "comments": _read_comments(path),
            **{name: fields.get(name, "") for name in FIELD_NAMES},
            "workType": meta.get("workType", ""),
        }

    def _task_view(self, path: Path) -> dict:
        meta = _read_meta(path)
        body = (path / "body.md").read_text(encoding="utf-8") if (path / "body.md").exists() else ""
        comments = _read_comments(path)
        return {
            "number": meta["number"],
            "title": meta["title"],
            "url": meta.get("url", ""),
            "state": meta.get("state", "OPEN"),
            "body": body,
            "comments": [comment["body"] for comment in comments],
            "commentObjects": comments,
            "taskId": meta.get("taskId"),
            "prs": _prs(meta),
        }

    # --- resolution ---

    def resolve(self, ref: str) -> WorkItem:
        return self._record_view(self._record_dir(ref))

    def queue_items(self) -> list[QueueItemSummary]:
        if not (_home() / "records").is_dir():
            return []
        records = sorted(
            (_home() / "records").iterdir(),
            key=lambda child: int(child.name) if child.name.isdigit() else 0,
        )
        summaries = []
        for child in records:
            if not child.is_dir():
                continue
            meta = _read_meta(child)
            fields = meta.get("fields", {})
            summaries.append({
                "id": meta["id"],
                "content": {
                    "number": meta["number"],
                    "title": meta.get("title") or "",
                    "url": meta.get("url") or "",
                },
                "Status": fields.get("Status", ""),
                "Gate State": fields.get("Gate State", ""),
                "Lifecycle": fields.get("Lifecycle", ""),
                "Skipped States": fields.get("Skipped States", ""),
                "workType": meta.get("workType", ""),
            })
        return summaries

    # --- state fields ---

    @single_writer
    def _set_fields(self, item_id: str, values: dict) -> None:
        number = str(item_id).removeprefix("FILE-")
        path = self._record_dir(number)
        meta = _read_meta(path)
        meta.setdefault("fields", {}).update(values)
        _write_meta(path, meta)

    def set_state(self, item_id: str, status: str, gate: str, lifecycle: str) -> None:
        self._set_fields(item_id, {"Status": status, "Gate State": gate, "Lifecycle": lifecycle})

    def set_gate(self, item_id: str, gate: str) -> None:
        self._set_fields(item_id, {"Gate State": gate})

    def set_slug(self, item_id: str, value: str) -> None:
        self._set_fields(item_id, {"Slug": value})

    def set_skipped_states(self, item_id: str, value: str) -> None:
        self._set_fields(item_id, {"Skipped States": value})

    @single_writer
    def close_record(self, ref: str) -> None:
        path = self._record_dir(ref)
        meta = _read_meta(path)
        meta["state"] = "CLOSED"
        _write_meta(path, meta)

    # --- body ---

    @single_writer
    def write_body(self, ref: str, body: str) -> None:
        atomic_write(self._record_dir(ref) / "body.md", body)

    # --- comments ---

    def comments(self, ref: str) -> list[Comment]:
        return _read_comments(self._entity_dir(ref))

    def comments_page(self, ref: str, page: int = 1, per_page: int = 100) -> CommentPage:
        if page < 1 or per_page != 100:
            raise PdlcError("comments page must be >= 1 and use 100 comments per page")
        comments = self.comments(ref)
        start = (page - 1) * per_page
        newest = list(reversed(comments))
        selected = newest[start:start + per_page]
        return CommentPage(selected, page, per_page, len(comments), start + len(selected) < len(comments))

    @single_writer
    def post_comment(self, ref: str, body: str) -> str:
        return _append_comment(self._entity_dir(ref), body, self.current_actor())

    @single_writer
    def edit_comment(self, ref: str, comment_ref: str, body: str) -> str:
        path = self._entity_dir(ref)
        comments = _read_comments(path)
        index = _comment_index(comments, comment_ref)
        comments[index] = {**comments[index], "body": body}
        atomic_write(path / "comments.jsonl", "".join(json.dumps(entry) + "\n" for entry in comments))
        return comment_ref

    @single_writer
    def delete_comment(self, ref: str, comment_ref: str) -> None:
        path = self._entity_dir(ref)
        comments = _read_comments(path)
        index = _comment_index(comments, comment_ref)
        del comments[index]
        atomic_write(path / "comments.jsonl", "".join(json.dumps(entry) + "\n" for entry in comments))

    @single_writer
    def post_blocker(self, ref: str, body: str) -> str:
        # Recorded in the same append-only log; the PDLC-DECISION marker makes it
        # findable. A future revision could also drop a `blocker` file in the
        # record dir for a cheap "is this record parked?" check.
        return _append_comment(self._entity_dir(ref), body, self.current_actor())

    # --- delivery tasks ---

    def _task_dirs(self, ref: str) -> list[Path]:
        tasks = self._record_dir(ref) / "tasks"
        if not tasks.is_dir():
            return []
        return sorted(
            (child for child in tasks.iterdir() if child.is_dir() and not _read_meta(child).get("removed")),
            key=lambda child: int(child.name),
        )

    def tasks(self, ref: str) -> list[Task]:
        return [self._task_view(path) for path in self._task_dirs(ref)]

    def tasks_by_number(self, numbers: list[str]) -> list[Task]:
        return [self._task_view(self._task_dir(number)) for number in numbers]

    @single_writer
    def upsert_tasks(self, parent: str, tasks: list[TaskInput], existing: list[Task]) -> list[TaskPublication]:
        by_id = {task["taskId"]: task for task in existing if task.get("taskId")}
        results = []
        for task in tasks:
            results.append(
                self._upsert(parent, task["id"], task["title"], task["bodyText"], by_id.get(task["id"]))
            )
        return results

    def _upsert(self, parent: str, task_id: str, title: str, body_text: str, match: dict | None) -> dict:
        full_title = f"WORK-{parent}-{task_id} {title}"
        record = self._record_dir(str(parent))

        if match:
            path = record / "tasks" / str(match["number"])
            meta = _read_meta(path)
            title_changed = meta.get("title") != full_title
            stored = (path / "body.md").read_text(encoding="utf-8") if (path / "body.md").exists() else ""
            body_changed = not same_task_body(stored, body_text)
            if title_changed or body_changed:
                meta["title"] = full_title
                _write_meta(path, meta)
                atomic_write(path / "body.md", body_text)
                action = "retitled" if title_changed else "updated"
            else:
                action = "unchanged"
            number = match["number"]
            url = meta.get("url", "")
        else:
            number = self._next_number()
            path = record / "tasks" / str(number)
            path.mkdir(parents=True)
            url = f"file://{path}"
            _write_meta(path, {
                "number": number, "title": full_title, "url": url,
                "state": "OPEN", "taskId": task_id,
            })
            atomic_write(path / "body.md", body_text)
            (path / "comments.jsonl").touch()
            action = "created"

        return {"action": action, "taskId": task_id, "number": number, "title": full_title, "url": url}

    @single_writer
    def close_task(self, task_ref: str) -> None:
        path = self._task_dir(task_ref)
        meta = _read_meta(path)
        meta["state"] = "CLOSED"
        _write_meta(path, meta)

    @single_writer
    def remove_task(self, parent: str, task_ref: str) -> None:
        path = self._record_dir(parent) / "tasks" / str(task_ref)
        if not path.is_dir():
            raise NotFound(f"no delivery task #{task_ref} under #{parent}")
        meta = _read_meta(path)
        meta["state"] = "CLOSED"
        meta["removed"] = True
        _write_meta(path, meta)

    @single_writer
    def reopen_task(self, task_ref: str) -> None:
        path = self._task_dir(task_ref)
        meta = _read_meta(path)
        meta["state"] = "OPEN"
        _write_meta(path, meta)

    def task_prs(self, ref: str) -> list[PullRef]:
        return sorted({pr for path in self._task_dirs(ref) for pr in _prs(_read_meta(path))})

    # --- attached pull requests ---

    # A `prs` array in the entity's own meta.json. Records and delivery tasks
    # both resolve through _entity_dir, so one implementation serves each, and
    # `body.md` stays plain human-authored Markdown. See `_pr_values`.

    @single_writer
    def attach_pr(self, ref: str, pr: PullRef) -> list[PullRef]:
        path = self._entity_dir(ref)
        meta = _read_meta(path)
        refs = sorted({*_prs(meta), pr})
        values = _pr_values(refs)
        if values != meta.get("prs"):
            meta["prs"] = values
            _write_meta(path, meta)
        return refs

    def attached_prs(self, ref: str) -> list[PullRef]:
        return _prs(_read_meta(self._entity_dir(ref)))

    # --- creation ---

    @single_writer
    def create(self, title: str, body: str, slug: str, work_type: WorkType = WorkType.FEATURE) -> CreatedRecord:
        work_type = self._validated_work_type(work_type)
        number = self._next_number()
        path = _home() / "records" / str(number)
        path.mkdir(parents=True)
        (path / "tasks").mkdir()
        (path / "comments.jsonl").touch()
        atomic_write(path / "body.md", body)
        url = f"file://{path}"
        _write_meta(path, {
            "id": f"FILE-{number}", "number": number, "title": title, "url": url,
            "workType": work_type.value,
            "fields": {name: "" for name in FIELD_NAMES},
        })
        return {"id": f"FILE-{number}", "number": number, "url": url}

    # --- identity ---

    def current_actor(self) -> str:
        return get_config().actor or "local"

    def ref_label(self) -> str:
        return get_config().ref_label or "pdlc"


# --- flat helpers ---

def _prs(meta: dict) -> list[PullRef]:
    return parse_pull_refs(meta.get("prs", []), get_config().pull_request_repository())


def _pr_values(refs: list[PullRef]) -> list[int | str]:
    """`prs` as stored: a bare number for a PR without a repository (the file
    code host's), else its `owner/name#N` token."""
    return [ref.number if not ref.repository else ref.token() for ref in refs]


def _read_meta(path: Path) -> dict:
    return json.loads((path / "meta.json").read_text(encoding="utf-8"))


def _write_meta(path: Path, meta: dict) -> None:
    atomic_write(path / "meta.json", json.dumps(meta, indent=2) + "\n")


def _read_comments(path: Path) -> list[dict]:
    log = path / "comments.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_comment(path: Path, body: str, actor: str) -> str:
    log = path / "comments.jsonl"
    existing = _read_comments(path)
    # The id is a monotonic counter persisted in meta.json, not the current
    # list length: once a comment is deleted, the list shrinks, but the next
    # id must still never collide with one a live comment's stored `url`
    # already carries.
    meta = _read_meta(path)
    next_id = int(meta.get("commentSeq") or 0) + 1
    _write_meta(path, {**meta, "commentSeq": next_id})
    url = f"{meta.get('url', '')}#comment-{next_id}"
    comment = {"body": body, "createdAt": _now(), "url": url, "author": {"login": actor}}
    atomic_write(log, "".join(json.dumps(entry) + "\n" for entry in [*existing, comment]))
    return url


# Comments are addressed by their own stored `url`, not by array position:
# once `delete_comment` can remove an entry, position drifts for everything
# appended after it, so a reference must resolve by identity, not index.
def _comment_index(comments: list[dict], comment_ref: str) -> int:
    for index, comment in enumerate(comments):
        if comment.get("url") == comment_ref:
            return index
    raise PdlcError(f"no such comment: {comment_ref}")
