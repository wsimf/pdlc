#!/usr/bin/env python3
"""Lands the Technical Plan stage in a single call: guards the record's
state, records each task's plan on its delivery task, and publishes the stage at
Approval Required.

    pdlc post plan --work-item N --manifest FILE --evidence FILE|- [--dry-run] [--attachment PATH [--attachment-description TEXT]]

Technical Plan is reviewed before this script publishes it. To rework a landed
plan, return it to Stale with pdlc post invalidate and re-run this script;
pdlc-inspect then reports the latest plan for each task. A record still at
`Technical Plan / Approval Required` is re-authored in place: a non-dry-run call
resets the stage to Stale itself (no comment — the plan never settled at
Approved, and the re-land's own evidence records the change) and re-lands the
reviewed plans.

The manifest is a JSON array naming the tasks this pass plans:

    [{"id": "TASK-003", "plan": "/tmp/plan-003.md"}]

Each plan file holds that task's plan content only, with no heading. The plan
is recorded as its own artifact on the task, so scope, non-goals,
dependencies, coverage, and acceptance criteria stay exactly as the Tasks
stage authored them.

A pass may plan a subset of tasks, as long as every open, unimplemented task
ends up with a plan (counting plans already recorded).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, validate_attachments  # type: ignore
from pdlc.internal.invalidation import reauthor_invalidate_stage  # type: ignore
from pdlc.internal.workitem import (  # type: ignore
    PLAN_COMMENT_HEADING,
    is_stage_skipped,
    item_gate,
    item_status,
    pipeline_for_item,
    post_comment,
    resolve_item,
    set_state,
    state_for_item,
    task_tree,
)
from pdlc.domain.lifecycle import (  # type: ignore
    PdlcError,
    duplicates,
    load_json_array,
    print_help,
    require_file,
    unmarked_evidence_source,
    wants_help,
)
from pdlc.domain.workflow import Event


def build_plan(tree: list[dict], replacements: list[dict]) -> dict:
    known = [task["taskId"] for task in tree if task.get("taskId") is not None]
    targeted = [entry["id"] for entry in replacements]
    untouched = [
        task for task in tree
        if task.get("needsPlan") and task.get("taskId") not in targeted
    ]

    errors: list[str] = []

    for task in tree:
        if task.get("taskId") is None:
            errors.append(f"delivery task #{task['number']} carries no stable task identity")

    for task_id in duplicates(targeted):
        errors.append(f"duplicate manifest entry: {task_id}")

    for task_id in targeted:
        if task_id not in known:
            errors.append(f"no such task on this record: {task_id}")

    for entry in replacements:
        if not entry["planText"].strip():
            errors.append(f"the plan file for {entry['id']} is empty")

    for task in tree:
        task_id = task.get("taskId")
        if task_id is not None and task_id in targeted and not task.get("needsPlan"):
            errors.append(f"{task_id} is closed or already implemented; it is not in scope for planning")

    left_unplanned = [task["taskId"] for task in untouched if not task.get("hasPlan")]
    if left_unplanned:
        errors.append(f"these tasks would be left unplanned: {', '.join(left_unplanned)}")

    already_planned = [task["taskId"] for task in untouched if task.get("hasPlan")]

    return {
        "targeted": targeted,
        "alreadyPlanned": already_planned,
        "errors": errors,
    }


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

    parser = argparse.ArgumentParser(description="Publish the Technical Plan stage")
    parser.add_argument("--work-item", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--evidence")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(script_args)

    scratch: list[Path] = []
    try:
        manifest_path = require_file("--manifest file", args.manifest)
        manifest = load_json_array("--manifest", manifest_path)
        validate_attachments(attachment_inputs)

        evidence_path: Path | None = None
        if not args.dry_run:
            if not args.evidence:
                raise PdlcError("--evidence FILE|- is required")
            evidence_path, is_temporary = unmarked_evidence_source("--evidence file", args.evidence)
            if is_temporary:
                scratch.append(evidence_path)

        record = resolve_item(args.work_item)
        pipeline = pipeline_for_item(record)
        item = record["id"]
        stage = item_status(record)
        gate = item_gate(record)

        if stage != "Technical Plan":
            raise PdlcError(f"cannot land Technical Plan: the record is at {stage}")
        if gate in ("Pending", "Stale"):
            pass
        elif gate == "Approval Required" and not args.dry_run:
            # The driver asked for a change before approving: reset Technical
            # Plan to Stale ourselves and re-land the reviewed plans in this call.
            reauthor_invalidate_stage(record, "Technical Plan", pipeline)
        elif gate == "Approval Required":
            raise PdlcError(f"Technical Plan is at {gate}; return it to Stale with pdlc post invalidate before re-planning it")
        elif gate in ("Review Required", "Changes Required"):
            raise PdlcError(f"Technical Plan is at {gate}, which no path in this flow produces for it; report it rather than landing over it")
        else:
            raise PdlcError(f"cannot land Technical Plan from Gate State: {gate or 'unset'}")
        if is_stage_skipped(record, "Technical Plan"):
            raise PdlcError("Technical Plan is declared in Skipped States; nothing to land")
        state = state_for_item(record, pipeline)
        try:
            target = pipeline.next_state(state, Event.PUBLISHED)
        except ValueError as error:
            raise PdlcError(str(error)) from None

        tree = task_tree(args.work_item)
        if not tree:
            raise PdlcError("no delivery tasks: the Tasks stage produced nothing to plan against")
        tree_by_id = {task["taskId"]: task for task in tree if task.get("taskId")}

        replacements: list[dict] = []
        for entry in manifest:
            task_id = entry.get("id") or ""
            path = entry.get("plan") or ""
            if not task_id:
                raise PdlcError('every manifest entry needs an "id"')
            plan_path = require_file(f"plan file for {task_id}", path)

            replacements.append({
                "id": task_id,
                "plan": str(plan_path),
                "planText": plan_path.read_text(),
            })

        plan = build_plan(tree, replacements)

        if plan["errors"]:
            print("pdlc: the plan does not fit the task tree it plans against:", file=sys.stderr)
            for error in plan["errors"]:
                print(f"  - {error}", file=sys.stderr)
            return 1

        if args.dry_run:
            print(json.dumps({
                "dryRun": True,
                "stage": "Technical Plan",
                "targeted": plan["targeted"],
                "alreadyPlanned": plan["alreadyPlanned"],
                "attachmentCount": len(attachment_inputs),
            }))
            return 0

        assert evidence_path is not None

        attachments = save_attachments(args.work_item, attachment_inputs)
        results = []
        for entry in replacements:
            task = tree_by_id[entry["id"]]
            body = f"{PLAN_COMMENT_HEADING}\n\n{entry['planText'].strip()}\n"
            post_comment(str(task["number"]), body)
            results.append({"taskId": entry["id"], "number": task["number"]})

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as handle:
            handle.write(evidence_path.read_text())
            handle.write("\n---\n\n")
            handle.write(f"Planned {len(results)} task(s): {', '.join(result['taskId'] for result in results)}\n")
            if plan["alreadyPlanned"]:
                handle.write(f"Already planned, left untouched by this pass: {', '.join(plan['alreadyPlanned'])}\n")
            summary_path = Path(handle.name)
        scratch.append(summary_path)

        post_comment(args.work_item, str(summary_path), "PLAN")
        set_state(item, target.stage, target.gate.value, target.lifecycle.value)

        print(json.dumps({
            "published": True,
            "stage": "Technical Plan",
            "itemId": item,
            "work_item": int(args.work_item),
            "gateState": target.gate.value,
            "planned": [result["taskId"] for result in results],
            "alreadyPlanned": plan["alreadyPlanned"],
            "tasks": results,
            "attachments": attachments,
        }))
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    finally:
        for path in scratch:
            path.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
