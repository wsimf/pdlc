"""Pure task identity, coverage, and dependency planning."""

from __future__ import annotations

import re

from pdlc.domain.lifecycle import PdlcError, duplicates
from pdlc.domain.model import CORE_TAG, UI_TAG

TASK_ID_FORMAT = re.compile(r"^TASK-[0-9]{3}$")


def declared_identifiers(text: str, pattern: re.Pattern) -> list[str]:
    return sorted(set(pattern.findall(text)))


# The [UI]/[CORE] tag pdlc-implement later reads back off the title to route
# a task to the UI or core implementation agent, without any other durable
# record of which agent a task belongs to. build_plan requires "ui" to be a strict bool
# before this ever runs, so the tag is never guessed from a falsy default.
def tagged_title(task: dict) -> str:
    tag = UI_TAG if task["ui"] else CORE_TAG
    return f"{tag} {task.get('title') or ''}"


def resolve_task_ids(tasks: list[dict], existing_ids: list[str]) -> list[dict]:
    malformed = [task["id"] for task in tasks if task.get("id") and not TASK_ID_FORMAT.fullmatch(task["id"])]
    if malformed:
        raise PdlcError("malformed task id: " + ", ".join(malformed))
    all_ids = [task["id"] for task in tasks if task.get("id")] + existing_ids
    highest = max((int(task_id.removeprefix("TASK-")) for task_id in all_ids), default=0)
    resolved = []
    next_number = highest + 1
    for task in tasks:
        if task.get("id"):
            resolved.append(dict(task))
        else:
            resolved.append({**task, "id": f"TASK-{next_number:03d}"})
            next_number += 1
    return resolved


def build_plan(resolved: list[dict], existing: list[dict], requirements: list[str], journeys: list[str]) -> dict:
    errors: list[str] = []
    # Validate manifest boundary types before applying set/regex operations;
    # malformed JSON should become a stable user error, never a traceback.
    for index, task in enumerate(resolved, 1):
        if "id" in task and not isinstance(task["id"], str):
            errors.append(f"manifest entry {index} id must be a string")
        if "title" in task and not isinstance(task["title"], str):
            errors.append(f"manifest entry {index} title must be a string")
        if not isinstance(task.get("covers", []), list) or not all(isinstance(v, str) for v in task.get("covers", [])):
            errors.append(f"manifest entry {index} covers must be an array of strings")
        if not isinstance(task.get("depends", []), list) or not all(isinstance(v, str) for v in task.get("depends", [])):
            errors.append(f"manifest entry {index} depends must be an array of strings")
    if errors:
        return {"tasks": resolved, "order": [], "cycle": [], "orphans": [], "errors": errors}

    ids = [task["id"] for task in resolved]
    id_set = set(ids)
    existing_ids = [task["taskId"] for task in existing if task.get("taskId")]
    existing_id_set = set(existing_ids)
    coverage_set = set(requirements) | set(journeys)

    ui_covered: set[str] = set()
    for task in resolved:
        if task.get("ui") is True:
            ui_covered.update(task.get("covers") or [])

    malformed_ids = [task_id for task_id in ids if not TASK_ID_FORMAT.match(task_id)]
    for task_id in malformed_ids:
        errors.append(f"malformed task id: {task_id}")

    for task_id in duplicates(ids):
        errors.append(f"duplicate task id: {task_id}")

    for title in duplicates([task.get("title") or "" for task in resolved]):
        errors.append(f"duplicate task title: {title}")

    for task in resolved:
        if not (task.get("title") or ""):
            errors.append(f"{task['id']} has no title")

    for task in resolved:
        if not isinstance(task.get("ui"), bool):
            errors.append(f"{task['id']} ui must be true or false, not {task.get('ui')!r}")

    for task in resolved:
        bad = sorted(set(task.get("covers") or []) - coverage_set)
        if bad:
            errors.append(f"{task['id']} covers {', '.join(bad)}, which the parent does not declare")

    for task in resolved:
        if not any(token.startswith(("FR-", "C-")) for token in (task.get("covers") or [])):
            errors.append(f"{task['id']} covers no FR-* or C-*")

    for task in resolved:
        if task.get("ui") is True and not any(token.startswith("UJ-") for token in (task.get("covers") or [])):
            errors.append(f"{task['id']} is a UI task but covers no UJ-*")

    for task in resolved:
        if task.get("ui") is not True and any(token.startswith("UJ-") for token in (task.get("covers") or [])):
            errors.append(f"{task['id']} covers a UJ-* but is not marked \"ui\": true")

    for journey in sorted(set(journeys) - ui_covered):
        errors.append(f"no UI task covers {journey}")

    for task in resolved:
        missing = sorted(set(task.get("depends") or []) - (id_set | existing_id_set))
        if missing:
            errors.append(f"{task['id']} depends on unknown {', '.join(missing)}")

    for task in resolved:
        if task["id"] in (task.get("depends") or []):
            errors.append(f"{task['id']} depends on itself")

    # Kahn: peel tasks whose dependencies are already ordered. A dependency on
    # an already-landed task that this manifest does NOT redefine is satisfied
    # from the start, so (existing_ids - ids) seeds the peeled set without
    # appearing in the printed order — an id this manifest reuses (updating
    # that task) is excluded from the seed so it still has to be peeled, and
    # can still be caught in a cycle, like any other task in resolved.
    # Anything left when nothing more can be peeled is in a cycle.
    done = existing_id_set - id_set
    order: list[str] = []
    left = list(resolved)
    for _ in range(len(resolved)):
        ready = sorted(task["id"] for task in left if not (set(task.get("depends") or []) - done))
        if not ready:
            break
        done |= set(ready)
        order.extend(ready)
        left = [task for task in left if task["id"] not in ready]

    if left:
        errors.append(f"dependency cycle: {', '.join(task['id'] for task in left)}")

    orphans = [task for task in existing if task.get("taskId") and task["taskId"] not in id_set]

    return {
        "tasks": resolved,
        "order": order,
        "cycle": [task["id"] for task in left],
        "orphans": orphans,
        "errors": errors,
    }
