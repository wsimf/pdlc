#!/usr/bin/env python3
"""NAME
    pdlc post plan - land the Technical Plan stage

USAGE
    pdlc post plan --work-item N --manifest FILE --evidence FILE|- [--dry-run] [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --dry-run    validate the plan and print a markdown report without landing it

DESCRIPTION
    Lands the Technical Plan stage in a single call: guards the record's
    state, records each task's plan on its delivery task, and publishes the stage at
    Approval Required.

Technical Plan is reviewed before this script publishes it. A task that
already carries a `## Technical Plan` comment has that comment replaced in
place rather than getting a second one, so pdlc-inspect and the task thread
only ever show one current plan per task. A record still at `Technical Plan /
Approval Required` is re-authored in place: a non-dry-run call overwrites the
existing plan comments with the new content (no invalidation comment — the
plan never settled at Approved, and the re-land's own evidence records the
change) and lands back at Approval Required, so it requires a fresh
independent review before the next approval.

`--dry-run` prints a markdown report:

    ## Technical Plan (dry run)

    Verdict: Pass
    Stage: Technical Plan
    Targeted: TASK-003
    Already planned: TASK-001, TASK-002
    Attachments: 0

    ## Passed Validations

    - <one bullet per check that passed>

    ## Failed Validations

    None.

    ## Warnings

    None.

Verdict is `Fail` and exits 1 if any check failed, with its specific errors
listed under Failed Validations instead of Passed Validations. When the
record is at `Technical Plan / Approval Required`, Warnings instead reads:
"This record is at Approval Required. Running this for real will overwrite
the existing plan in place with the new content. Only proceed if that's the
driver's intention — confirm with the user first if it isn't already clear
from the conversation." Dry run never mutates the record regardless of gate
state.

The manifest is a JSON array naming the tasks this pass plans:

    [{"id": "TASK-003", "plan": "/tmp/plan-003.md"}]

Each plan file holds that task's plan content only, with no heading. The plan
is recorded as its own artifact on the task, so scope, non-goals,
dependencies, coverage, and acceptance criteria stay exactly as the Tasks
stage authored them.

A pass may plan a subset of tasks, as long as every open task ends up with a
plan (counting plans already recorded).
"""

from __future__ import annotations

import argparse
import json
import sys


from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, validate_attachments
from pdlc.internal.invalidation import reauthor_invalidate_stage
from pdlc.internal.workitem import (
    PLAN_COMMENT_HEADING,
    edit_comment,
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
from pdlc.domain.lifecycle import PdlcError, duplicates
from pdlc.internal.inputs import assert_unmarked, load_json_array, print_help, require_file, resolve_text, wants_help
from pdlc.domain.workflow import Event


def build_plan(tree: list[dict], replacements: list[dict]) -> dict:
    known = [task["taskId"] for task in tree if task.get("taskId") is not None]
    targeted = [entry["id"] for entry in replacements]
    # Scope is every OPEN task, not just unplanned ones: a targeted task already
    # carrying a plan is a legitimate re-land-in-place, not an error, so
    # eligibility is checked on state alone here, not on `needsPlan`.
    untouched = [
        task for task in tree
        if task.get("state") == "OPEN" and task.get("taskId") not in targeted
    ]

    left_unplanned = [task["taskId"] for task in untouched if not task.get("hasPlan")]

    # Each check is named so dry-run can report which validations passed
    # alongside which failed, rather than only surfacing failures.
    checks = [
        ("every delivery task carries a stable task identity", [
            f"delivery task #{task['number']} carries no stable task identity"
            for task in tree if task.get("taskId") is None
        ]),
        ("no duplicate manifest entries", [
            f"duplicate manifest entry: {task_id}" for task_id in duplicates(targeted)
        ]),
        ("every manifest entry matches a task on this record", [
            f"no such task on this record: {task_id}" for task_id in targeted if task_id not in known
        ]),
        ("no empty plan files", [
            f"the plan file for {entry['id']} is empty"
            for entry in replacements if not entry["planText"].strip()
        ]),
        ("no targeted task is closed", [
            f"{task['taskId']} is closed; it is not in scope for planning"
            for task in tree
            if task.get("taskId") is not None and task["taskId"] in targeted and task.get("state") != "OPEN"
        ]),
        ("every open task ends up with a plan", (
            [f"these tasks would be left unplanned: {', '.join(left_unplanned)}"] if left_unplanned else []
        )),
    ]

    errors = [error for _, group in checks for error in group]
    already_planned = [task["taskId"] for task in untouched if task.get("hasPlan")]

    return {
        "targeted": targeted,
        "alreadyPlanned": already_planned,
        "errors": errors,
        "checks": checks,
    }


def _render_dry_run(gate: str, plan: dict, attachment_count: int) -> str:
    passed = [label for label, group in plan["checks"] if not group]
    failed = [error for _, group in plan["checks"] for error in group]
    verdict = "Fail" if failed else "Pass"

    lines = [
        "## Technical Plan (dry run)",
        "",
        f"Verdict: {verdict}",
        "Stage: Technical Plan",
        f"Targeted: {', '.join(plan['targeted']) if plan['targeted'] else 'None'}",
        f"Already planned: {', '.join(plan['alreadyPlanned']) if plan['alreadyPlanned'] else 'None'}",
        f"Attachments: {attachment_count}",
        "",
        "## Passed Validations",
        "",
        "\n".join(f"- {label}" for label in passed) if passed else "None.",
        "",
        "## Failed Validations",
        "",
        "\n".join(f"- {error}" for error in failed) if failed else "None.",
        "",
        "## Warnings",
        "",
    ]
    if gate == "Approval Required":
        lines.append(
            "- This record is at Approval Required. Running this for real will overwrite "
            "the existing plan in place with the new content. Only proceed if that's the "
            "driver's intention — confirm with the user first if it isn't already clear "
            "from the conversation."
        )
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw_args = command_args
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

    try:
        manifest_path = require_file("--manifest file", args.manifest)
        manifest = load_json_array("--manifest", manifest_path)
        validate_attachments(attachment_inputs)

        evidence_body: str | None = None
        if not args.dry_run:
            if not args.evidence:
                raise PdlcError("--evidence FILE|- is required")
            evidence_body = resolve_text(args.evidence, label="--evidence")
            assert_unmarked(evidence_body, "--evidence")

        record = resolve_item(args.work_item)
        pipeline = pipeline_for_item(record)
        item = record["id"]
        stage = item_status(record)
        gate = item_gate(record)

        if stage != "Technical Plan":
            raise PdlcError(f"cannot land Technical Plan: the record is at {stage}")
        if gate in ("Pending", "Stale"):
            pass
        elif gate == "Approval Required":
            # Defer this mutation until the complete manifest has validated.
            # Invalid plans must leave the approval gate untouched. A dry run
            # never reaches the mutation at all, so it is safe to preview here.
            pass
        elif gate in ("Review Required", "Changes Required"):
            raise PdlcError(f"Technical Plan is at {gate}, which no path in this flow produces for it; report it rather than landing over it")
        else:
            raise PdlcError(f"cannot land Technical Plan from Gate State: {gate or 'unset'}")
        if is_stage_skipped(record, "Technical Plan"):
            raise PdlcError("Technical Plan is declared in Skipped States; nothing to land")
        tree = task_tree(args.work_item)
        if not tree:
            raise PdlcError("no delivery tasks: the Tasks stage produced nothing to plan against")
        tree_by_id = {task["taskId"]: task for task in tree if task.get("taskId")}

        replacements: list[dict] = []
        for index, entry in enumerate(manifest, 1):
            task_id = entry.get("id") or ""
            path = entry.get("plan") or ""
            if not isinstance(task_id, str):
                raise PdlcError(f"manifest entry {index} id must be a string")
            if not isinstance(path, str):
                raise PdlcError(f"manifest entry {index} plan must be a file path string")
            if not task_id:
                raise PdlcError('every manifest entry needs an "id"')
            plan_path = require_file(f"plan file for {task_id}", path)

            replacements.append({
                "id": task_id,
                "plan": str(plan_path),
                "planText": plan_path.read_text(encoding="utf-8"),
            })

        plan = build_plan(tree, replacements)

        if args.dry_run:
            sys.stdout.write(_render_dry_run(gate, plan, len(attachment_inputs)))
            return 1 if plan["errors"] else 0

        if plan["errors"]:
            print("pdlc: the plan does not fit the task tree it plans against:", file=sys.stderr)
            for error in plan["errors"]:
                print(f"  - {error}", file=sys.stderr)
            return 1

        assert evidence_body is not None

        if gate == "Approval Required":
            reauthor_invalidate_stage(record, "Technical Plan", pipeline)

        state = state_for_item(record, pipeline)
        try:
            target = pipeline.next_state(state, Event.PUBLISHED)
        except ValueError as error:
            raise PdlcError(str(error)) from None

        attachments = save_attachments(args.work_item, attachment_inputs)
        results = []
        for entry in replacements:
            task = tree_by_id[entry["id"]]
            body = f"{PLAN_COMMENT_HEADING}\n\n{entry['planText'].strip()}\n"
            existing = task.get("planCommentUrl")
            if existing:
                edit_comment(str(task["number"]), existing, body)
            else:
                post_comment(str(task["number"]), body)
            results.append({"taskId": entry["id"], "number": task["number"]})

        summary = (
            f"{evidence_body}\n---\n\n"
            f"Planned {len(results)} task(s): {', '.join(result['taskId'] for result in results)}\n"
        )
        if plan["alreadyPlanned"]:
            summary += f"Already planned, left untouched by this pass: {', '.join(plan['alreadyPlanned'])}\n"

        post_comment(args.work_item, summary, "PLAN")
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
