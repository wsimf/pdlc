"""The one import surface for the `pdlc-*` scripts to reach a PDLC record.

Pure logic (section editing, task classification, routing, field accessors) is
re-exported straight from `pdlc_model`. Everything that touches the backing
store goes through `workitem_host.get_backend()`, so the scripts never name a
backend and a swap is one env var.
"""

from __future__ import annotations

from pdlc_common import PdlcError, read_body_source as _read_source
from pdlc_model import (  # noqa: F401  (re-exported for the scripts)
    CORE_TAG,
    IMPLEMENTATION_COMMENT_HEADING,
    PLAN_COMMENT_HEADING,
    UI_TAG,
    classify_task,
    compose_comment,
    due_next,
    invalidations_by_stage,
    is_stage_skipped,
    item_gate,
    item_issue,
    item_skipped_states,
    item_slug,
    item_status,
    read_section,
    splice_section,
)
from pdlc_model import find_marked_comments as _model_find_marked_comments
from pdlc_model import marked_comments as _model_marked_comments
from pdlc_model import timeline_compact as _model_timeline_compact
from pdlc_model import timeline_markdown as _model_timeline_markdown
from workitem_host import get_backend

UPDATABLE_SECTIONS = {"Product", "UI", "Decisions", "Open Questions", "Verification"}


# --- resolution / state ---

def resolve_item(ref: str) -> dict:
    return get_backend().resolve(str(ref))


item_for_issue = resolve_item


def project_items() -> dict:
    return get_backend().all_items()


def set_state(item_id: str, status: str, gate: str, lifecycle: str) -> None:
    get_backend().set_state(item_id, status, gate, lifecycle)


def set_gate(item_id: str, gate: str) -> None:
    get_backend().set_gate(item_id, gate)


def set_slug(item_id: str, value: str) -> None:
    get_backend().set_slug(item_id, value)


def set_skipped_states(item_id: str, value: str) -> None:
    get_backend().set_skipped_states(item_id, value)


def current_actor() -> str:
    return get_backend().current_actor()


def ref_label() -> str:
    return get_backend().ref_label()


# --- body sections ---

def _write_sections(ref: str, fragments: dict[str, str]) -> None:
    invalid = set(fragments) - UPDATABLE_SECTIONS
    if invalid:
        raise PdlcError(f"unsupported work-item section: {', '.join(sorted(invalid))}")
    backend = get_backend()
    original = backend.resolve(str(ref)).get("issueBody") or ""
    updated = original
    for section, fragment in fragments.items():
        updated = splice_section(updated, section, fragment)
    if updated != original:
        backend.write_body(str(ref), updated)


def update_section(ref: str, section: str, fragment: str) -> None:
    _write_sections(ref, {section: fragment})


def update_sections(ref: str, fragments: dict[str, str]) -> None:
    if fragments:
        _write_sections(ref, fragments)


def append_to_section(ref: str, section: str, lines: list[str]) -> None:
    if not lines:
        return
    if section not in UPDATABLE_SECTIONS:
        raise PdlcError(f"unsupported work-item section: {section}")
    backend = get_backend()
    body = backend.resolve(str(ref)).get("issueBody") or ""
    existing = read_section(body, section).rstrip("\n")
    addition = "\n".join(f"- {line}" for line in lines)
    fragment = f"{existing}\n{addition}" if existing else addition
    backend.write_body(str(ref), splice_section(body, section, fragment))


def write_body(ref: str, body: str) -> None:
    get_backend().write_body(str(ref), body)


# --- comments ---

def comments_for_issue(ref: str) -> list[dict]:
    return get_backend().comments(str(ref))


def post_comment(ref: str, text_or_file: str, marker: str | None = None) -> str:
    body = compose_comment(marker, _read_source(text_or_file))
    return get_backend().post_comment(str(ref), body)


def post_blocker(ref: str, text_or_file: str, marker: str | None = None) -> str:
    """Post a blocking review decision through the backend's blocker channel.
    Same body/marker composition as post_comment; the backend decides how
    prominently to surface it."""
    body = compose_comment(marker, _read_source(text_or_file))
    return get_backend().post_blocker(str(ref), body)


def find_marked_comments(ref: str, marker: str, *, comments: list[dict] | None = None) -> list[dict]:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_find_marked_comments(snapshot, marker)


def marked_comments(ref: str, *, comments: list[dict] | None = None) -> list[dict]:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_marked_comments(snapshot)


def timeline_markdown(ref: str, *, comments: list[dict] | None = None) -> str:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_timeline_markdown(snapshot)


def timeline_compact(ref: str, file_path: str, *, comments: list[dict] | None = None) -> str:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_timeline_compact(snapshot, file_path)


# --- delivery tasks ---

def subissues_for(ref: str) -> list[dict]:
    return [classify_task(task) for task in get_backend().tasks(str(ref))]


task_tree = subissues_for


def tasks_by_number(numbers: list[str]) -> list[dict]:
    return [classify_task(task) for task in get_backend().tasks_by_number([str(n) for n in numbers])]


def require_all_subissues_closed(ref: str) -> None:
    open_numbers = [str(task["number"]) for task in get_backend().tasks(str(ref)) if task["state"] != "CLOSED"]
    if open_numbers:
        raise PdlcError(f"open delivery tasks prevent this transition: {','.join(open_numbers)}")


def upsert_tasks(parent: str, tasks: list[dict], existing: list[dict]) -> list[dict]:
    return get_backend().upsert_tasks(str(parent), tasks, existing)


def close_task(task_ref: str) -> None:
    get_backend().close_task(str(task_ref))


# --- creation ---

def create_work_item(title: str, body: str, slug: str) -> dict:
    return get_backend().create(title, body, slug)
