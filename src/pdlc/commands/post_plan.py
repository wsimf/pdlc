#!/usr/bin/env python3
"""NAME
    pdlc post plan - land the Technical Plan stage

USAGE
    pdlc post plan --work-item N --manifest FILE --evidence FILE|- [--dry-run] [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --work-item N                        required; the work item's number
    --manifest FILE                      required; the plan manifest `pdlc prompt tech-planner` generated
    --evidence FILE|-                    required unless --dry-run; the review evidence body
    --dry-run                            validate the plan and print a markdown report without landing it
    --attachment PATH (repeatable)       attach a local file's contents to the evidence comment
    --attachment-description TEXT        description for the --attachment immediately before it

DESCRIPTION
    Lands the Technical Plan stage: records each task's plan on its
    delivery task and publishes the stage at Approval Required.

Technical Plan is reviewed before this script publishes it. A task that
already carries a `## Technical Plan` comment has that comment replaced in
place rather than getting a second one, so pdlc-inspect and the task thread
only ever show one current plan per task. A record still at `Technical Plan /
Approval Required` (or `Review Required`) is re-authored in place: a non-dry-run call overwrites the
existing plan comments with the new content (no invalidation comment — the
plan never settled at Approved, and the re-land's own evidence records the
change) and lands back at Approval Required, so it requires a fresh
independent review before the next approval.

The record must be at `Technical Plan` with Gate State `Pending`, `Stale`,
`Changes Required`, `Review Required`, or `Approval Required`. `Changes
Required` (for example after a resolved decision) lands the same way as
`Stale`. `Review Required` (a plan published without its local review) is
re-authored in place the same way as `Approval Required`. `Decision Required`
is refused with a pointer to `pdlc guide decisions`; any other gate is
refused. A refusal leaves the record untouched.

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
listed under Failed Validations instead of Passed Validations. `Targeted`
names the tasks whose plan this call writes; `Already planned` names the
tasks whose recorded plan it leaves as it is. When the record is at
`Technical Plan / Approval Required`, Warnings instead reads: "This record is
at Approval Required. Running this for real will overwrite the existing plan
in place with the new content. Only proceed if that's the driver's intention —
confirm with the user first if it isn't already clear from the conversation."
Dry run never mutates the record regardless of gate state; it may restore the
local review files, as described below.

The manifest is the one `pdlc prompt tech-planner` generates, one entry per
open, unimplemented delivery task:

    [{"id": "TASK-003", "number": 413, "title": "[CORE] Render elevation profile",
      "file": "<cache>/pdlc-tech-planner-TASK-003.md", "baseline": "<sha256>"}]

Every field is generated; none is edited. Each task file holds the task body
between `--- BEGIN TASK ---` and `--- END TASK ---`, then the plan between
`--- BEGIN TECH PLAN ---` and `--- END TECH PLAN ---`, with nothing outside
the two blocks. Only the plan block lands: HTML comments are stripped from it,
and what remains must be non-empty and hold no `#` or `##` heading. The task
body is a read-only copy; an edit to it fails validation and is refused,
because the plan must fit the task as recorded, and a change the task needs is
a blocker to report. A task body or plan that changed on the record since the
manifest was generated is refused as stale, unless the record already holds
exactly this file's content, as it does after an interrupted landing.

The manifest names exactly the open, unimplemented tasks, and every other open
task must already have a plan. Only plans that differ from the recorded plan
are written, so a re-run after a partial landing skips the plans that already
landed. The plan is recorded as its own artifact on the task, so scope,
non-goals, dependencies, coverage, and acceptance criteria stay exactly as the
Tasks stage authored them.

Only reviewed files land. `pdlc prompt plan-reviewer` records the exact
manifest and task files it hands the reviewer. If any of them changed since,
this command restores each to the reviewed version, keeps the edited copy
beside it as `<name>.rejected.md`, and refuses so the review is redone; a
real landing also refuses a manifest the reviewer was not handed. After a
successful landing the manifest's baselines are rewritten onto the recorded
plans, so reusing it later changes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, validate_attachments
from pdlc.internal.invalidation import reauthor_invalidate_stage
from pdlc.internal.review_stamp import clear_stamp, require_reviewed, restore_reviewed
from pdlc.internal.scratch import replace_file
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
from pdlc.domain.plan_file import (
    PlanFile,
    manifest_errors,
    parse,
    plan_baseline,
    plan_errors,
    planner_command,
    regenerate,
    reviewer_command,
    same_plan,
    same_task,
    stored_plan,
)
from pdlc.internal.inputs import assert_unmarked, load_json_array, print_help, require_file, resolve_text, wants_help
from pdlc.domain.workflow import Event, decision_required_message
from pdlc.internal.failure import Recovery, report_failure, set_recovery

STAGE = "Technical Plan"


def _in_scope(task: dict) -> bool:
    """A task this stage plans: open and not yet implemented."""
    return bool(task.get("taskId")) and task.get("state") == "OPEN" and not task.get("hasImplementation")


def _read_file(entry: dict) -> tuple[PlanFile | None, list[str]]:
    path = Path(entry["file"])
    if not path.is_file():
        return None, [f"its task file does not exist: {path}"]
    return parse(path.read_text(encoding="utf-8"))


def build_plan(tree: list[dict], entries: list[dict], work_item: str) -> dict:
    """Check the manifest against the task tree and sort its plans into the
    ones this call writes and the ones already recorded as they stand."""
    by_id = {task["taskId"]: task for task in tree if task.get("taskId")}
    scope = [task["taskId"] for task in tree if _in_scope(task)]
    named = [entry["id"] for entry in entries]
    unknown: list[str] = []
    numbers: list[str] = []
    files: list[str] = []
    stale: list[str] = []
    edited: list[str] = []
    plans: list[str] = []
    targeted: list[dict] = []
    unchanged: list[str] = []

    for entry in entries:
        task_id = entry["id"]
        task = by_id.get(task_id)
        if task is None or not _in_scope(task):
            unknown.append(f"{task_id} is not an open, unimplemented task of this record; {regenerate(work_item)}")
            continue
        if entry["number"] != task["number"]:
            numbers.append(f"{task_id} is task #{task['number']}, not #{entry['number']}; {regenerate(work_item)}")
            continue
        planned, errors = _read_file(entry)
        if planned is None:
            files.extend(f"{task_id} file {entry['file']}: {error}; {regenerate(work_item)}" for error in errors)
            continue
        body = task.get("body") or ""
        recorded = stored_plan(task.get("planComment"))
        if plan_baseline(body, recorded) != entry["baseline"]:
            # An interrupted landing already recorded this exact content.
            if not (same_task(planned.task, body) and same_plan(planned.plan, recorded)):
                stale.append(f"{task_id} changed on the record after this manifest was generated; {regenerate(work_item)}")
                continue
        if not same_task(planned.task, body):
            edited.append(
                f"{task_id}: the task body between `--- BEGIN TASK ---` and `--- END TASK ---` was edited. The task"
                " body is read-only in this stage: pdlc lands only the tech plan, and the plan must fit the task as"
                f" recorded. Restore it from the record (`pdlc inspect task {task_id}`) and report the needed task"
                " change as a blocker instead"
            )
            continue
        errors = plan_errors(planned.plan)
        if errors:
            plans.extend(f"{task_id} ({entry['file']}): {error}" for error in errors)
            continue
        if same_plan(planned.plan, recorded):
            unchanged.append(task_id)
        else:
            targeted.append({"id": task_id, "task": task, "plan": planned.plan})

    left_unplanned = [
        task["taskId"] for task in tree
        if task.get("taskId") and task.get("state") == "OPEN" and task["taskId"] not in named and not task.get("hasPlan")
    ]
    # Each check is named so dry-run can report which validations passed
    # alongside which failed, rather than only surfacing failures.
    checks = [
        ("every delivery task carries a stable task identity", [
            f"delivery task #{task['number']} carries no stable task identity"
            for task in tree if task.get("taskId") is None
        ]),
        ("no duplicate manifest entries", [
            f"duplicate manifest entry: {task_id}" for task_id in duplicates(named)
        ]),
        ("every manifest entry names an open, unimplemented task", unknown),
        ("the manifest names every open, unimplemented task", [
            f"{task_id} is open and unimplemented but missing from the manifest; {regenerate(work_item)}"
            for task_id in scope if task_id not in named
        ]),
        ("every manifest entry carries its task's number", numbers),
        ("every task file keeps its task and tech plan blocks", files),
        ("no task changed on the record since the manifest was generated", stale),
        ("no task body was edited", edited),
        ("every tech plan is non-empty and heading-free", plans),
        ("every open task ends up with a plan", (
            [f"these tasks would be left unplanned: {', '.join(left_unplanned)}"] if left_unplanned else []
        )),
    ]

    errors = [error for _, group in checks for error in group]
    already_planned = unchanged + [
        task["taskId"] for task in tree
        if task.get("taskId") and task.get("state") == "OPEN" and task["taskId"] not in named and task.get("hasPlan")
    ]
    return {
        "targeted": [write["id"] for write in targeted],
        "writes": targeted,
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


def _load_manifest(manifest_path: Path, work_item: str) -> list[dict]:
    entries = load_json_array("--manifest", manifest_path)
    errors = manifest_errors(entries)
    if errors:
        listed = "\n".join(f"  - {error}" for error in errors)
        raise PdlcError(f"the manifest is not the one pdlc generated:\n{listed}\n{regenerate(work_item)}")
    return entries


def _rebase_manifest(manifest_path: Path, entries: list[dict], tree: list[dict]) -> None:
    """Point every baseline at the plans as now recorded, so reusing the
    manifest reads as unchanged rather than stale."""
    by_id = {task["taskId"]: task for task in tree if task.get("taskId")}
    rebased = []
    for entry in entries:
        planned, _ = _read_file(entry)
        task = by_id[entry["id"]]
        plan = planned.plan if planned is not None else stored_plan(task.get("planComment"))
        rebased.append({**entry, "baseline": plan_baseline(task.get("body") or "", plan)})
    replace_file(manifest_path, json.dumps(rebased, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw_args = command_args
    if wants_help(raw_args):
        print_help(__doc__)
        return 0

    try:
        script_args, attachment_inputs = parse_attachment_arguments(raw_args)
    except PdlcError as error:
        return report_failure(error)

    parser = argparse.ArgumentParser(description="Publish the Technical Plan stage")
    parser.add_argument("--work-item", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--evidence")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(script_args)

    try:
        manifest_path = require_file("--manifest file", args.manifest).resolve()
        rereview = reviewer_command(args.work_item, manifest_path)
        # A reviewed file edited since its review is put back before anything reads it.
        restore_reviewed(args.work_item, STAGE, rereview, planner_command(args.work_item, manifest_path))
        entries = _load_manifest(manifest_path, args.work_item)
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

        if stage != STAGE:
            raise PdlcError(f"cannot land Technical Plan: the record is at {stage}")
        # Changes Required lands exactly like Stale: a resolved decision parks
        # the stage there, and the re-planned artifact publishes from it.
        if gate in ("Pending", "Stale", "Changes Required"):
            pass
        elif gate in ("Review Required", "Approval Required"):
            # Defer this mutation until the complete manifest has validated.
            # Invalid plans must leave the published gate untouched. A dry run
            # never reaches the mutation at all, so it is safe to preview here.
            pass
        elif gate == "Decision Required":
            raise PdlcError(decision_required_message(stage))
        else:
            raise PdlcError(f"cannot land Technical Plan from Gate State: {gate or 'unset'}")
        if is_stage_skipped(record, STAGE):
            raise PdlcError("Technical Plan is declared in Skipped States; nothing to land")
        set_recovery(Recovery(
            check=f"pdlc inspect {args.work_item}",
            landed="the gate is Review Required and `pdlc inspect task T` shows the new plan on every task in the manifest",
            note="A re-run skips plans that already landed, but after the PDLC-PLAN evidence landed it posts a second one; mention it in your report.",
        ))
        tree = task_tree(args.work_item)
        if not tree:
            raise PdlcError("no delivery tasks: the Tasks stage produced nothing to plan against")

        plan = build_plan(tree, entries, args.work_item)

        if args.dry_run:
            sys.stdout.write(_render_dry_run(gate, plan, len(attachment_inputs)))
            return 1 if plan["errors"] else 0

        if plan["errors"]:
            print("pdlc: the plan does not fit the task tree it plans against:", file=sys.stderr)
            for error in plan["errors"]:
                print(f"  - {error}", file=sys.stderr)
            return 1

        require_reviewed(args.work_item, STAGE, manifest_path, rereview)
        assert evidence_body is not None

        if gate in ("Review Required", "Approval Required"):
            reauthor_invalidate_stage(record, STAGE, pipeline)

        state = state_for_item(record, pipeline)
        try:
            target = pipeline.next_state(state, Event.PUBLISHED)
        except ValueError as error:
            raise PdlcError(str(error)) from None

        attachments = save_attachments(args.work_item, attachment_inputs)
        results = []
        for write in plan["writes"]:
            task = write["task"]
            body = f"{PLAN_COMMENT_HEADING}\n\n{write['plan']}\n"
            existing = task.get("planCommentUrl")
            if existing:
                edit_comment(str(task["number"]), existing, body)
            else:
                post_comment(str(task["number"]), body)
            results.append({"taskId": write["id"], "number": task["number"]})

        planned_line = (
            f"Planned {len(results)} task(s): {', '.join(result['taskId'] for result in results)}\n" if results
            else "Planned 0 task(s): every reviewed plan was already recorded\n"
        )
        summary = f"{evidence_body}\n---\n\n{planned_line}"
        if plan["alreadyPlanned"]:
            summary += f"Already planned, left untouched by this pass: {', '.join(plan['alreadyPlanned'])}\n"

        post_comment(args.work_item, summary, "PLAN")
        set_state(item, target.stage, target.gate.value, target.lifecycle.value)

        # The landing is done; a manifest left un-rebased is only a hazard to warn about.
        try:
            _rebase_manifest(manifest_path, entries, tree)
            clear_stamp(args.work_item, STAGE)
        except (OSError, PdlcError) as error:
            print(f"pdlc: warning: published, but could not rebase {manifest_path} onto the recorded plans: {error};"
                  " do not reuse it", file=sys.stderr)

        print(json.dumps({
            "published": True,
            "stage": STAGE,
            "itemId": item,
            "work_item": int(args.work_item),
            "gateState": target.gate.value,
            "planned": [result["taskId"] for result in results],
            "alreadyPlanned": plan["alreadyPlanned"],
            "tasks": results,
            "attachments": attachments,
        }))
    except PdlcError as error:
        return report_failure(error)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
