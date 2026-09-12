"""The one import surface for the `pdlc-*` scripts to reach a PDLC record.

Pure logic (section editing, task classification, routing, field accessors) is
re-exported straight from `pdlc.domain.model`. Everything that touches the backing
store goes through `workitem_host.get_backend()`, so the scripts never name a
backend and a swap is one env var.
"""

from __future__ import annotations

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.workflow import Lifecycle, PIPELINES, Pipeline, State, WorkType
from pdlc.domain.model import (  # noqa: F401  (re-exported for the scripts)
    CORE_TAG,
    IMPLEMENTATION_COMMENT_HEADING,
    PLAN_COMMENT_HEADING,
    UI_TAG,
    classify_task,
    compose_comment,
    due_next,
    heading_comment_objects,
    is_stage_skipped,
    item_gate,
    item_issue,
    item_skipped_states,
    item_slug,
    item_status,
    task_title,
    read_section,
    splice_section,
)
from pdlc.domain.model import find_marked_comments as _model_find_marked_comments
from pdlc.domain.model import marked_comments as _model_marked_comments
from pdlc.domain.model import task_timeline_compact as _model_task_timeline_compact
from pdlc.domain.model import task_timeline_markdown as _model_task_timeline_markdown
from pdlc.domain.model import timeline_compact as _model_timeline_compact
from pdlc.domain.model import timeline_markdown as _model_timeline_markdown
from pdlc.domain.model import user_comments as _model_user_comments
from pdlc.domain.model import user_comments_markdown as _model_user_comments_markdown
from pdlc.domain.model import verification_evidence_comments as _model_verification_evidence_comments
from pdlc.domain.records import Comment, CreatedRecord, Task, TaskPublication, WorkItem, validate_work_item, validate_task, validate_task_inputs
from pdlc.hosts.workitem_host import get_backend
from pdlc.hosts.workitem_host.base import QueueItemSummary

UPDATABLE_SECTIONS = {"Product", "UI", "Decisions", "Open Questions", "Verification"}


# --- resolution / state ---

def resolve_item(ref: str) -> WorkItem:
    return validate_work_item(get_backend().resolve(str(ref)))


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

def comments_for_issue(ref: str) -> list[Comment]:
    return get_backend().comments(str(ref))

def comments_page(ref: str, page: int = 1):
    return get_backend().comments_page(str(ref), page, 100)


def post_comment(ref: str, body: str, marker: str | None = None) -> str:
    """Post `body` as-is under an optional `PDLC-<marker>` line. Callers resolve
    a file/stdin argument to text with `inputs.resolve_text` before calling."""
    return get_backend().post_comment(str(ref), compose_comment(marker, body))


def edit_comment(ref: str, comment_ref: str, body: str, marker: str | None = None) -> str:
    """Replace an existing comment's body in place, addressed by the
    reference `post_comment` returned for it. Same marker composition as
    `post_comment`."""
    return get_backend().edit_comment(str(ref), comment_ref, compose_comment(marker, body))


def delete_comment(ref: str, comment_ref: str) -> None:
    """Permanently remove an existing comment, addressed by the reference
    `post_comment` returned for it."""
    get_backend().delete_comment(str(ref), comment_ref)


def post_blocker(ref: str, body: str, marker: str | None = None) -> str:
    """Post a blocking review decision through the backend's blocker channel.
    Same body/marker composition as post_comment; the backend decides how
    prominently to surface it."""
    return get_backend().post_blocker(str(ref), compose_comment(marker, body))


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
    if comments is None:
        page = comments_page(ref, 1)
        snapshot = page.comments
        older = page.total - len(snapshot)
    else:
        snapshot = list(reversed(comments[-100:]))
        older = max(0, len(comments) - len(snapshot))
    rendered = _model_user_comments_markdown(snapshot)
    if older:
        rendered += f"\n\n{older} more comments; use pdlc inspect comments {ref} --page 2"
    return rendered


def timeline_compact(ref: str, file_path: str, *, comments: list[dict] | None = None) -> str:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_timeline_compact(snapshot, file_path)


def task_timeline_markdown(ref: str, *, comments: list[dict] | None = None) -> str:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_task_timeline_markdown(snapshot)


def task_timeline_compact(ref: str, file_path: str, *, comments: list[dict] | None = None) -> str:
    snapshot = comments if comments is not None else comments_for_issue(ref)
    return _model_task_timeline_compact(snapshot, file_path)


# --- delivery tasks ---

def subissues_for(ref: str) -> list[Task]:
    return [classify_task(validate_task(task)) for task in get_backend().tasks(str(ref))]


task_tree = subissues_for


def tasks_by_number(numbers: list[str]) -> list[Task]:
    return [classify_task(validate_task(task)) for task in get_backend().tasks_by_number([str(n) for n in numbers])]


def require_all_subissues_closed(ref: str) -> None:
    open_numbers = [str(task["number"]) for task in get_backend().tasks(str(ref)) if task["state"] != "CLOSED"]
    if open_numbers:
        raise PdlcError(f"open delivery tasks prevent this transition: {','.join(open_numbers)}")


def upsert_tasks(parent: str, tasks: list[dict], existing: list[Task]) -> list[TaskPublication]:
    return get_backend().upsert_tasks(str(parent), validate_task_inputs(tasks), existing)


def close_task(task_ref: str) -> None:
    get_backend().close_task(str(task_ref))


def reopen_task(task_ref: str) -> None:
    get_backend().reopen_task(str(task_ref))


def attach_pr(ref: str, pr_number: int) -> list[int]:
    """Attach `pr_number` to a record or one of its delivery tasks, so later
    stages read its pull requests explicitly rather than inferring them from a
    PR body or a branch name. Idempotent; returns the full list.

    Where the backend keeps the link is its own concern — see
    `WorkItemBackend.attach_pr`."""
    return get_backend().attach_pr(str(ref), int(pr_number))


def attached_prs(ref: str) -> list[int]:
    """Every pull request attached to `ref`, ascending."""
    return get_backend().attached_prs(str(ref))


# --- creation ---

def create_work_item(title: str, body: str, slug: str, work_type: WorkType = WorkType.FEATURE) -> CreatedRecord:
    return get_backend().create(title, body, slug, work_type)
