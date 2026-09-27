"""A delivery task and its technical plan as one editable planner file.

`pdlc prompt tech-planner` writes one file per task; the planner edits only
the tech plan block, the reviewer reads the same file, and `pdlc post plan`
lands that block. The task block is a read-only copy of the stored task body,
which `pdlc post plan` checks was left unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from pdlc.domain.model import PLAN_COMMENT_HEADING
from pdlc.domain.task_artifact import normalized_task_body

TASK_BEGIN = "--- BEGIN TASK ---"
TASK_END = "--- END TASK ---"
PLAN_BEGIN = "--- BEGIN TECH PLAN ---"
PLAN_END = "--- END TECH PLAN ---"
EMPTY_PLAN = "<!-- Tech plan is empty: write this task's plan here. -->"

_MARKERS = (TASK_BEGIN, TASK_END, PLAN_BEGIN, PLAN_END)
_FENCE = re.compile(r"^ {0,3}(```|~~~)")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def planner_command(work_item: str, manifest: object) -> str:
    """The brief that starts a planning pass on an existing plan manifest."""
    return f"pdlc prompt tech-planner {work_item} --current-plan-manifest-path {manifest} --file"


def reviewer_command(work_item: str, manifest: object) -> str:
    """The brief that hands a plan manifest to its reviewer."""
    return f"pdlc prompt plan-reviewer {work_item} --manifest {manifest} --file"


def regenerate(work_item: str) -> str:
    """The recovery for a plan manifest that no longer matches the record."""
    return (f"run `pdlc prompt tech-planner {work_item}` for fresh task files, re-dispatch the tech planner"
            " agent with them, and review its plans again")


_MANIFEST_FIELDS: tuple[tuple[str, type], ...] = (
    ("id", str), ("number", int), ("title", str), ("file", str), ("baseline", str),
)


def manifest_errors(entries: list[dict]) -> list[str]:
    """Why a plan manifest no longer has the shape `pdlc prompt tech-planner` generates."""
    errors: list[str] = []
    for index, entry in enumerate(entries, 1):
        label = entry["id"] if isinstance(entry.get("id"), str) and entry["id"] else f"manifest entry {index}"
        for field, kind in _MANIFEST_FIELDS:
            value = entry.get(field)
            if not isinstance(value, kind) or isinstance(value, bool) or (kind is str and not value):
                errors.append(f"{label} needs its generated {field!r}")
        extra = sorted(set(entry) - {field for field, _ in _MANIFEST_FIELDS})
        if extra:
            errors.append(f"{label} carries fields the manifest does not take: {', '.join(extra)}")
    return errors


@dataclass(frozen=True)
class PlanFile:
    task: str
    plan: str


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _unfenced(lines: list[str]) -> list[tuple[int, str]]:
    """Each line outside a code fence, with its index."""
    kept: list[tuple[int, str]] = []
    fenced = False
    for index, line in enumerate(lines):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            kept.append((index, line))
    return kept


def render(task_body: str, plan: str) -> str:
    """The file the planner edits: the task body, then its plan or a placeholder."""
    return (
        f"{TASK_BEGIN}\n\n{task_body.strip()}\n\n{TASK_END}\n\n"
        f"{PLAN_BEGIN}\n\n{plan.strip() or EMPTY_PLAN}\n\n{PLAN_END}\n"
    )


def parse(text: str) -> tuple[PlanFile | None, list[str]]:
    """The task and plan blocks, or why the file no longer has that shape."""
    lines = _lines(text)
    found: dict[str, list[int]] = {marker: [] for marker in _MARKERS}
    for index, line in _unfenced(lines):
        if line.strip() in found:
            found[line.strip()].append(index)
    errors = [
        f"`{marker}` must appear exactly once on its own line, found {len(indexes)}"
        for marker, indexes in found.items() if len(indexes) != 1
    ]
    if errors:
        return None, errors
    task_begin, task_end, plan_begin, plan_end = (found[marker][0] for marker in _MARKERS)
    if not task_begin < task_end < plan_begin < plan_end:
        return None, [f"the markers must appear in the order {', '.join(f'`{marker}`' for marker in _MARKERS)}"]
    outside = lines[:task_begin] + lines[task_end + 1:plan_begin] + lines[plan_end + 1:]
    if any(line.strip() for line in outside):
        return None, ["the file holds text outside the task and tech plan blocks; write only between the tech plan markers"]
    task = "\n".join(lines[task_begin + 1:task_end]).strip()
    # A plan that opens with its own `## Technical Plan` line would land it twice.
    plan = stored_plan(_COMMENT.sub("", "\n".join(lines[plan_begin + 1:plan_end])))
    return PlanFile(task=task, plan=plan), []


def plan_errors(plan: str) -> list[str]:
    """What stops a plan landing as the body of its `## Technical Plan` comment."""
    if not plan.strip():
        return ["the tech plan is empty; write this task's plan between the tech plan markers"]
    return []


def stored_plan(comment: str | None) -> str:
    """A task's recorded plan without its heading, or empty when it has none."""
    lines = _lines((comment or "").strip())
    if lines and lines[0].strip() == PLAN_COMMENT_HEADING:
        lines = lines[1:]
    return "\n".join(lines).strip()


def same_plan(left: str, right: str) -> bool:
    return "\n".join(_lines(left)).strip() == "\n".join(_lines(right)).strip()


def same_task(file_task: str, stored_body: str) -> bool:
    """Whether the file's task block still matches the stored task body."""
    return normalized_task_body(file_task.strip()) == normalized_task_body(stored_body.strip())


def plan_baseline(task_body: str, plan: str) -> str:
    """Fingerprint a task's stored body and plan, so a stale file is refused."""
    payload = json.dumps(
        {"body": normalized_task_body(task_body.strip()), "plan": "\n".join(_lines(plan)).strip()},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
