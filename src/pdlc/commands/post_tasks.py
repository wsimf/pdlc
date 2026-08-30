#!/usr/bin/env python3
"""Lands one pdlc-tasks stage in a single call: guards the record's state,
validates the artifact against the parent's own requirements, lands it,
and publishes the stage at Approval Required.

UI and Tasks are reviewed before they are published — pdlc-tasks runs that
review on the local files, so what lands is already reviewed and
needs only the driver's approval. Neither stage ever enters Review Required,
and since pdlc post review is the only thing that sets Changes Required, neither
reaches that either: their gate set is Pending, Stale, Approval Required,
Approved. A landed artifact is reworked by returning it to Stale with
pdlc post invalidate. A record still at `<stage> / Approval Required` is
re-authored in place: a non-dry-run call resets the stage to Stale itself (no
comment — the artifact never settled at Approved, and the re-land's own evidence
records the change) and re-lands the reviewed artifact.

    pdlc post tasks --work-item N --stage UI    --body FILE     --evidence FILE|- [--dry-run] [--attachment PATH [--attachment-description TEXT]]
    pdlc post tasks --work-item N --stage Tasks --manifest FILE --evidence FILE|- [--dry-run] [--attachment PATH [--attachment-description TEXT]]

Everything is validated before anything is written, so a manifest with a
typo'd requirement or a dependency cycle fails without having touched the
record. --dry-run stops after validation and prints the plan, which is how a
breakdown is checked before it is worth landing.

UI --body is the `## UI` section's content; a leading `## UI` heading is
tolerated and stripped. Applicability must be explicit: the fragment either
names at least one `UJ-N` journey, or states that no UI is required.

Tasks --manifest is a JSON array, one entry per delivery task:

    [
      {
        "id": "TASK-001",              optional; assigned from the next free
                                       number when absent
        "title": "Persist route profile geometry",
                                       human-readable half only — the script
                                       composes the stable WORK-N-TASK-NNN
        "body": "/tmp/task-001.md",    the delivery task body
        "ui": false,                   true when the task delivers UI
        "covers": ["FR-2", "C-1"],     FR-*/C-*/UJ-* this task delivers
        "depends": ["TASK-001"]        tasks that must land first
      }
    ]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path


from pdlc.internal.workitem import (  # type: ignore
    CORE_TAG,
    UI_TAG,
    is_stage_skipped,
    item_gate,
    item_status,
    post_comment,
    read_section,
    resolve_item,
    set_state,
    splice_section,
    subissues_for,
    upsert_tasks,
    write_body,
)
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, validate_attachments  # type: ignore
from pdlc.internal.invalidation import reauthor_invalidate_stage  # type: ignore
from pdlc.domain.lifecycle import (  # type: ignore
    PdlcError,
    duplicates,
    load_json_array,
    print_help,
    require_file,
    unmarked_evidence_source,
    wants_help,
)

TASK_ID_FORMAT = re.compile(r"^TASK-[0-9]{3}$")
FR_C_PATTERN = re.compile(r"\b(?:FR|C)-[0-9]+\b")
UJ_PATTERN = re.compile(r"\bUJ-[0-9]+\b")
UI_HEADING_PATTERN = re.compile(r"^##[ \t]+UI[ \t]*$")
NO_UI_PATTERN = re.compile(r"no UI is required|UI is not required|UI not required", re.IGNORECASE)


def declared_identifiers(text: str, pattern: re.Pattern) -> list[str]:
    return sorted(set(pattern.findall(text)))


# The [UI]/[CORE] tag pdlc-implement later reads back off the title to route
# a task to swiftui-pro or swift-pro, without any other durable record of
# which agent a task belongs to. build_plan requires "ui" to be a strict bool
# before this ever runs, so the tag is never guessed from a falsy default.
def tagged_title(task: dict) -> str:
    tag = UI_TAG if task["ui"] else CORE_TAG
    return f"{tag} {task.get('title') or ''}"


def resolve_task_ids(tasks: list[dict], existing_ids: list[str]) -> list[dict]:
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
    ids = [task["id"] for task in resolved]
    id_set = set(ids)
    existing_ids = [task["taskId"] for task in existing if task.get("taskId")]
    existing_id_set = set(existing_ids)
    coverage_set = set(requirements) | set(journeys)

    ui_covered: set[str] = set()
    for task in resolved:
        if task.get("ui") is True:
            ui_covered.update(task.get("covers") or [])

    errors: list[str] = []

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


def land_ui(issue: str, item: str, parent_body: str, body_path: Path, evidence_path: Path, dry_run: bool, attachment_inputs: list[dict]) -> None:
    lines = body_path.read_text().splitlines()
    if lines and UI_HEADING_PATTERN.match(lines[0]):
        lines = lines[1:]
    fragment = "\n".join(lines)
    if not fragment.strip():
        raise PdlcError(f"--body file holds nothing but its heading: {body_path}")

    if not (UJ_PATTERN.search(fragment) or NO_UI_PATTERN.search(fragment)):
        raise PdlcError(
            "UI applicability must be explicit: name at least one UJ-N journey, "
            "or state that no UI is required"
        )

    journeys = declared_identifiers(fragment, UJ_PATTERN)

    if dry_run:
        print(json.dumps({"dryRun": True, "stage": "UI", "journeys": journeys, "attachmentCount": len(attachment_inputs)}))
        return

    attachments = save_attachments(issue, attachment_inputs)
    spliced = splice_section(parent_body, "UI", fragment)
    write_body(str(issue), spliced)

    post_comment(issue, str(evidence_path), "UI")
    set_state(item, "UI", "Approval Required", "Planning")

    print(json.dumps({
        "published": True,
        "stage": "UI",
        "itemId": item,
        "work_item": int(issue),
        "journeys": journeys,
        "gateState": "Approval Required",
        "attachments": attachments,
    }))


def land_tasks(issue: str, item: str, manifest_path: Path, evidence_path: Path | None, dry_run: bool, parent_body: str, attachment_inputs: list[dict]) -> None:
    manifest = load_json_array("--manifest", manifest_path, allow_empty=False)

    for task in manifest:
        require_file("task body file", task.get("body"))

    existing = subissues_for(issue)
    existing_ids = [task["taskId"] for task in existing if task.get("taskId")]

    requirements = declared_identifiers(read_section(parent_body, "Product"), FR_C_PATTERN)
    journeys = declared_identifiers(read_section(parent_body, "UI"), UJ_PATTERN)

    resolved = resolve_task_ids(manifest, existing_ids)
    plan = build_plan(resolved, existing, requirements, journeys)

    if plan["errors"]:
        print("pdlc: the task breakdown does not satisfy the parent record:", file=sys.stderr)
        for error in plan["errors"]:
            print(f"  - {error}", file=sys.stderr)
        raise SystemExit(1)

    if dry_run:
        print(json.dumps({
            "dryRun": True,
            "stage": "Tasks",
            "tasks": [
                {
                    "id": task["id"],
                    "title": tagged_title(task),
                    "ui": task.get("ui"),
                    "covers": task.get("covers"),
                    "depends": task.get("depends") or [],
                }
                for task in plan["tasks"]
            ],
            "order": plan["order"],
            "orphans": [task["taskId"] for task in plan["orphans"]],
            "attachmentCount": len(attachment_inputs),
        }))
        return

    attachments = save_attachments(issue, attachment_inputs)
    results = upsert_tasks(issue, [
        {**task, "title": tagged_title(task)} for task in plan["tasks"]
    ], existing)

    created = [r["taskId"] for r in results if r["action"] == "created"]
    updated = [r["taskId"] for r in results if r["action"] == "updated"]
    retitled = [r["taskId"] for r in results if r["action"] == "retitled"]
    unchanged = [r["taskId"] for r in results if r["action"] == "unchanged"]
    open_orphans = [task["taskId"] for task in plan["orphans"] if task.get("state") != "CLOSED"]

    # The evidence body is the durable judgement. Counts, order, and coverage
    # are already recoverable from the task tree and should not inflate history.
    summary_lines = [evidence_path.read_text().rstrip("\n")]
    if open_orphans:
        summary_lines += ["", f"Exception: open tasks absent from this breakdown: {', '.join(open_orphans)}"]

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as handle:
        handle.write("\n".join(summary_lines) + "\n")
        summary_path = handle.name
    try:
        post_comment(issue, summary_path, "TASKS")
    finally:
        Path(summary_path).unlink(missing_ok=True)

    set_state(item, "Tasks", "Approval Required", "Planning")

    print(json.dumps({
        "published": True,
        "stage": "Tasks",
        "itemId": item,
        "work_item": int(issue),
        "gateState": "Approval Required",
        "created": created,
        "updated": updated,
        "retitled": retitled,
        "unchanged": unchanged,
        "orphans": open_orphans,
        "order": plan["order"],
        "tasks": results,
        "attachments": attachments,
    }))


def main() -> int:
    raw_args = sys.argv[1:]
    if wants_help(raw_args):
        print_help(__doc__)
        return 0

    try:
        script_args, attachment_inputs = parse_attachment_arguments(raw_args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="Land a pdlc-tasks stage")
    parser.add_argument("--work-item", required=True)
    parser.add_argument("--stage", required=True, choices=["UI", "Tasks"])
    parser.add_argument("--body")
    parser.add_argument("--manifest")
    parser.add_argument("--evidence")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(script_args)

    scratch: list[Path] = []
    body_path: Path | None = None
    manifest_path: Path | None = None
    try:
        if args.stage == "UI":
            if not args.body:
                raise PdlcError("--stage UI requires --body FILE")
            if args.manifest:
                raise PdlcError("--manifest is only valid with --stage Tasks")
            body_path = require_file("--body file", args.body)
        else:
            if not args.manifest:
                raise PdlcError("--stage Tasks requires --manifest FILE")
            if args.body:
                raise PdlcError("--body is only valid with --stage UI")
            manifest_path = require_file("--manifest file", args.manifest)

        validate_attachments(attachment_inputs)

        # Evidence is slurped and checked up front so a publish can never
        # fail for a missing body after the artifact has already been
        # written.
        evidence_path: Path | None = None
        if not args.dry_run:
            if not args.evidence:
                raise PdlcError("--evidence FILE|- is required")
            evidence_path, is_temporary = unmarked_evidence_source("--evidence file", args.evidence)
            if is_temporary:
                scratch.append(evidence_path)

        # Guard the record's state
        #
        # The gate check is what stops a second authoring pass from posting
        # over an artifact that is already awaiting review or approval and
        # silently destroying a pending approval.
        record = resolve_item(args.work_item)
        item = record["id"]
        current_stage = item_status(record)
        gate = item_gate(record)

        if current_stage != args.stage:
            raise PdlcError(f"cannot land {args.stage}: the record is at {current_stage}")
        if gate in ("Pending", "Stale"):
            pass
        elif gate == "Approval Required" and not args.dry_run:
            # The driver asked for a change before approving: reset the stage to
            # Stale ourselves and re-land the reviewed artifact in this call.
            reauthor_invalidate_stage(record, args.stage)
        elif gate == "Approval Required":
            raise PdlcError(f"{args.stage} is at {gate}; return it to Stale with pdlc post invalidate before re-authoring it")
        elif gate in ("Review Required", "Changes Required"):
            raise PdlcError(f"{args.stage} is at {gate}, which no path in this flow produces for {args.stage}; report it rather than landing over it")
        else:
            raise PdlcError(f"cannot land {args.stage} from Gate State: {gate or 'unset'}")
        if is_stage_skipped(record, args.stage):
            raise PdlcError(f"{args.stage} is declared in Skipped States; nothing to land")

        parent_body = record.get("issueBody") or ""

        if args.stage == "UI":
            land_ui(args.work_item, item, parent_body, body_path, evidence_path, args.dry_run, attachment_inputs)
        else:
            land_tasks(args.work_item, item, manifest_path, evidence_path, args.dry_run, parent_body, attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    finally:
        for path in scratch:
            path.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
