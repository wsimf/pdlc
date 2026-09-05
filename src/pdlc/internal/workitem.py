"""The one import surface for the `pdlc-*` scripts to reach a PDLC record.

Pure logic (section editing, task classification, routing, field accessors) is
re-exported straight from `pdlc_model`. Everything that touches the backing
store goes through `workitem_host.get_backend()`, so the scripts never name a
backend and a swap is one env var.
"""

from __future__ import annotations

from pdlc.domain.lifecycle import PdlcError, read_body_source as _read_source
from pdlc.domain.workflow import Lifecycle, PIPELINES, Pipeline, State, WorkType
from pdlc.domain.model import (  # noqa: F401  (re-exported for the scripts)
    CORE_TAG,
    IMPLEMENTATION_COMMENT_HEADING,
    PLAN_COMMENT_HEADING,
    UI_TAG,
    classify_task,
    compose_comment,
    due_next,
    is_stage_skipped,
    item_gate,
    item_issue,
    item_skipped_states,
    item_slug,
    item_status,
    read_section,
    read_task_meta,
    splice_section,
    strip_task_meta,
    task_prs,
    write_task_meta,
)
from pdlc.domain.model import find_marked_comments as _model_find_marked_comments
from pdlc.domain.model import marked_comments as _model_marked_comments
from pdlc.domain.model import timeline_compact as _model_timeline_compact
from pdlc.domain.model import timeline_markdown as _model_timeline_markdown
from pdlc.domain.model import user_comments as _model_user_comments
from pdlc.domain.model import user_comments_markdown as _model_user_comments_markdown
from pdlc.domain.model import verification_evidence_comments as _model_verification_evidence_comments
from pdlc.hosts.workitem_host import get_backend
from pdlc.hosts.workitem_host.base import QueueItemSummary

UPDATABLE_SECTIONS = {"Product", "UI", "Decisions", "Open Questions", "Verification"}


# --- resolution / state ---

def resolve_item(ref: str) -> dict:
    return get_backend().resolve(str(ref))


item_for_issue = resolve_item


def pipeline_for_item(item: dict) -> Pipeline:
    """Resolve one record's pipeline, including legacy Feature compatibility."""
    try:
        return PIPELINES.for_record(item)
    except (TypeError, ValueError) as error:
        raise PdlcError(str(error)) from None


def state_for_item(item: dict, pipeline: Pipeline) -> State:
    """Parse and validate one record's persisted state against its pipeline."""
    try:
        status = item_status(item)
        lifecycle = item.get("Lifecycle") or (
            Lifecycle.COMPLETED if status == pipeline.terminal_stage else Lifecycle.PLANNING
        )
        state = State.parse(status, item_gate(item), lifecycle)
        pipeline.validate_state(state)
        return state
    except (TypeError, ValueError) as error:
        raise PdlcError(str(error)) from None


def workflow_for_item(item: dict) -> tuple[Pipeline, State]:
    """Resolve one record's pipeline and validate its persisted state once."""
    pipeline = pipeline_for_item(item)
    return pipeline, state_for_item(item, pipeline)


def queue_items() -> list[QueueItemSummary]:
    return get_backend().queue_items()


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


def verification_evidence_comments(ref: str, *, comments: list[dict] | None = None) -> list[dict]:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_verification_evidence_comments(snapshot)


def marked_comments(ref: str, *, comments: list[dict] | None = None) -> list[dict]:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_marked_comments(snapshot)


def timeline_markdown(ref: str, *, comments: list[dict] | None = None) -> str:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_timeline_markdown(snapshot)


def user_comments(ref: str, *, comments: list[dict] | None = None) -> list[dict]:
    """Comments on the record that carry no `PDLC-*` marker — human or outside-bot
    discussion the marker-only timeline hides. Pass `comments` to reuse a snapshot
    already fetched in the same call."""
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_user_comments(snapshot)


def user_comments_markdown(ref: str, *, comments: list[dict] | None = None) -> str:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_user_comments_markdown(snapshot)


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


def _register_pr(body: str, pr_number: int, write) -> list[int]:
    """Upsert `pr_number` into a body's machine-owned metadata block, persisting
    through `write` only when it changes. Returns the full list.

    This is a read-modify-write over the whole body: a concurrent body edit
    between the caller's read and `write` would be lost. Acceptable while these
    calls are serialized by one agent per record; revisit if the body becomes
    genuinely concurrently written.
    """
    current = task_prs(body)
    if pr_number in current:
        return current
    updated = sorted({*current, pr_number})
    meta = read_task_meta(body)
    meta["prs"] = [str(n) for n in updated]
    write(write_task_meta(body, meta))
    return updated


def register_task_pr(task_ref: str, pr_number: int) -> list[int]:
    """Record `pr_number` on a delivery task so later stages read the task's
    pull requests explicitly rather than inferring them from a PR body or a
    branch name. Idempotent; returns the full list."""
    backend = get_backend()
    body = backend.tasks_by_number([str(task_ref)])[0].get("body") or ""
    return _register_pr(body, pr_number, lambda new: backend.write_task_body(str(task_ref), new))


def register_record_pr(ref: str, pr_number: int) -> list[int]:
    """Record `pr_number` on a record itself — the linear (non-stacked) flow's
    one shared implementation pull request. Idempotent; returns the full list."""
    backend = get_backend()
    body = backend.resolve(str(ref)).get("issueBody") or ""
    return _register_pr(body, pr_number, lambda new: backend.write_body(str(ref), new))


# --- creation ---

def create_work_item(title: str, body: str, slug: str, work_type: WorkType = WorkType.FEATURE) -> dict:
    return get_backend().create(title, body, slug, work_type)
