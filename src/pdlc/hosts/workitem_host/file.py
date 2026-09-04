"""File work-item backend: a PDLC record is a directory under `$PDLC_HOME`
(default `.pdlc`), its state is a JSON file, its body is `body.md`, its
evidence is an append-only `comments.jsonl`, and its delivery tasks are
child directories under `tasks/`.

    $PDLC_HOME/
      seq                        shared monotonic counter (records + tasks)
      records/<n>/
        meta.json                {id, number, title, url, fields:{...}}
        body.md
        comments.jsonl
        tasks/<m>/
          meta.json              {number, title, url, state, taskId}
          body.md
          comments.jsonl

The store mirrors GitHub closely enough that the `pdlc-*` scripts and the
`workitem` facade cannot tell the two apart: records and tasks share one
number space, tasks keep a stable `WORK-<n>-TASK-NNN` identity, and comments
are never edited in place.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import WorkType
from pdlc.domain.model import read_task_meta, strip_task_meta, write_task_meta
from pdlc.hosts.workitem_host.base import WorkItemBackend

FIELD_NAMES = ("Status", "Gate State", "Lifecycle", "Skipped States", "Slug")


def _home() -> Path:
    root = Path(os.environ.get("PDLC_HOME", ".pdlc"))
    (root / "records").mkdir(parents=True, exist_ok=True)
    return root


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FileWorkItemBackend(WorkItemBackend):
    capabilities = {"subissue_graph", "queue_scan"}

    # --- number allocation ---

    def _next_number(self) -> int:
        seq = _home() / "seq"
        current = int(seq.read_text()) if seq.exists() else 0
        current += 1
        seq.write_text(str(current))
        return current

    # --- record directories ---

    def _record_dir(self, ref: str) -> Path:
        records = _home() / "records"
        ref = str(ref)
        if ref.isdigit():
            path = records / ref
            if not path.is_dir():
                raise PdlcError(f"no PDLC record for #{ref}")
            return path
        matches = [
            child for child in records.iterdir()
            if child.is_dir() and _read_meta(child).get("fields", {}).get("Slug") == ref
        ]
        if not matches:
            raise PdlcError(f"no PDLC record with slug: {ref}")
        if len(matches) > 1:
            raise PdlcError(f"slug is ambiguous: {ref}")
        return matches[0]

    def _task_dir(self, number: str) -> Path:
        number = str(number)
        for record in (_home() / "records").iterdir():
            candidate = record / "tasks" / number
            if candidate.is_dir():
                return candidate
        raise PdlcError(f"no delivery task for #{number}")

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
        body = (path / "body.md").read_text() if (path / "body.md").exists() else ""
        return {
            "id": meta["id"],
            "number": meta["number"],
            "content": {"number": meta["number"], "title": meta.get("title"), "url": meta.get("url")},
            "issueBody": body,
            "comments": _read_comments(path),
            **{name: fields.get(name, "") for name in FIELD_NAMES},
            "workType": meta.get("workType", ""),
        }

    def _task_view(self, path: Path) -> dict:
        meta = _read_meta(path)
        body = (path / "body.md").read_text() if (path / "body.md").exists() else ""
        return {
            "number": meta["number"],
            "title": meta["title"],
            "url": meta.get("url", ""),
            "state": meta.get("state", "OPEN"),
            "body": body,
            "comments": [comment["body"] for comment in _read_comments(path)],
            "taskId": meta.get("taskId"),
        }

    # --- resolution ---

    def resolve(self, ref: str) -> dict:
        return self._record_view(self._record_dir(ref))

    def all_items(self) -> dict:
        records = sorted(
            (_home() / "records").iterdir(),
            key=lambda child: int(child.name) if child.name.isdigit() else 0,
        )
        return {"items": [self._record_view(child) for child in records if child.is_dir()]}

    # --- state fields ---

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

    # --- body ---

    def write_body(self, ref: str, body: str) -> None:
        (self._record_dir(ref) / "body.md").write_text(body)

    # --- comments ---

    def comments(self, ref: str) -> list[dict]:
        return _read_comments(self._entity_dir(ref))

    def post_comment(self, ref: str, body: str) -> str:
        return _append_comment(self._entity_dir(ref), body, self.current_actor())

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
            (child for child in tasks.iterdir() if child.is_dir()),
            key=lambda child: int(child.name),
        )

    def tasks(self, ref: str) -> list[dict]:
        return [self._task_view(path) for path in self._task_dirs(ref)]

    def tasks_by_number(self, numbers: list[str]) -> list[dict]:
        return [self._task_view(self._task_dir(number)) for number in numbers]

    def upsert_tasks(self, parent: str, tasks: list[dict], existing: list[dict]) -> list[dict]:
        by_id = {task["taskId"]: task for task in existing if task.get("taskId")}
        results = []
        for task in tasks:
            results.append(
                self._upsert(parent, task["id"], task["title"], task["body"], by_id.get(task["id"]))
            )
        return results

    def _upsert(self, parent: str, task_id: str, title: str, body_path: str, match: dict | None) -> dict:
        full_title = f"WORK-{parent}-{task_id} {title}"
        body_text = Path(body_path).read_text()
        record = self._record_dir(str(parent))

        if match:
            path = record / "tasks" / str(match["number"])
            meta = _read_meta(path)
            title_changed = meta.get("title") != full_title
            stored = (path / "body.md").read_text() if (path / "body.md").exists() else ""
            # The machine-owned `pdlc:meta` block is preserved across a re-plan,
            # not counted as a body change.
            preserved_meta = read_task_meta(stored)
            body_changed = strip_task_meta(stored) != body_text
            if title_changed or body_changed:
                meta["title"] = full_title
                _write_meta(path, meta)
                (path / "body.md").write_text(write_task_meta(body_text, preserved_meta))
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
            (path / "body.md").write_text(body_text)
            (path / "comments.jsonl").touch()
            action = "created"

        return {"action": action, "taskId": task_id, "number": number, "title": full_title, "url": url}

    def write_task_body(self, task_ref: str, body: str) -> None:
        (self._task_dir(task_ref) / "body.md").write_text(body)

    def close_task(self, task_ref: str) -> None:
        path = self._task_dir(task_ref)
        meta = _read_meta(path)
        meta["state"] = "CLOSED"
        _write_meta(path, meta)

    # --- creation ---

    def create(self, title: str, body: str, slug: str, work_type: WorkType = WorkType.FEATURE) -> dict:
        work_type = self._validated_work_type(work_type)
        number = self._next_number()
        path = _home() / "records" / str(number)
        path.mkdir(parents=True)
        (path / "tasks").mkdir()
        (path / "comments.jsonl").touch()
        (path / "body.md").write_text(body)
        url = f"file://{path}"
        _write_meta(path, {
            "id": f"FILE-{number}", "number": number, "title": title, "url": url,
            "workType": work_type.value,
            "fields": {name: "" for name in FIELD_NAMES},
        })
        return {"id": f"FILE-{number}", "number": number, "url": url}

    # --- identity ---

    def current_actor(self) -> str:
        return os.environ.get("PDLC_ACTOR", "local")

    def ref_label(self) -> str:
        return os.environ.get("PDLC_REF_LABEL", "pdlc")


# --- flat helpers ---

def _read_meta(path: Path) -> dict:
    return json.loads((path / "meta.json").read_text())


def _write_meta(path: Path, meta: dict) -> None:
    (path / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")


def _read_comments(path: Path) -> list[dict]:
    log = path / "comments.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def _append_comment(path: Path, body: str, actor: str) -> str:
    log = path / "comments.jsonl"
    existing = _read_comments(path)
    url = f"{_read_meta(path).get('url', '')}#comment-{len(existing) + 1}"
    comment = {"body": body, "createdAt": _now(), "url": url, "author": {"login": actor}}
    with log.open("a") as handle:
        handle.write(json.dumps(comment) + "\n")
    return url
