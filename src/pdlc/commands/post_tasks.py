#!/usr/bin/env python3
"""NAME
    pdlc post tasks - land the UI or Tasks stage

USAGE
    - if landing the UI stage:
        pdlc post tasks --work-item N --stage UI    --body FILE     --evidence FILE|- [--dry-run] [--attachment PATH [--attachment-description TEXT]]
    - if landing the Tasks stage:
        pdlc post tasks --work-item N --stage Tasks --manifest FILE --evidence FILE|- [--dry-run] [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --work-item N                        required; the work item's number
    --stage UI|Tasks                     required; which stage this call lands
    --body FILE                          required with --stage UI; the `## UI` section's content
    --manifest FILE                      required with --stage Tasks; JSON array of delivery tasks
    --evidence FILE|-                    required unless --dry-run; the review evidence body
    --dry-run                            validate and print the plan without landing it
    --attachment PATH (repeatable)       attach a local file's contents to the evidence comment
    --attachment-description TEXT        description for the --attachment immediately before it

DESCRIPTION
    Lands the UI or Tasks stage: validates the artifact against the
    parent's own requirements, lands it, and publishes the stage at
    Approval Required.

UI and Tasks are reviewed before they are published — pdlc-tasks runs that
review on the local files, so what lands is already reviewed and
needs only the driver's approval. The stage lands from Pending, Stale, or
Changes Required (where a resolved decision parks it). A record at
`<stage> / Review Required` (published without its local review) or
`<stage> / Approval Required` (a driver change request) is re-authored in
place: a non-dry-run call resets the stage to Stale itself (no comment — the
artifact never settled at Approved, and the re-land's own evidence records the
change) and re-lands the reviewed artifact. A dry run at Approval Required is
refused; return the stage to Stale with pdlc post invalidate first. Decision
Required is refused with a pointer to `pdlc guide decisions`; any other gate
is refused. An approved artifact is reworked by returning it to Stale with
pdlc post invalidate.

Everything is validated before anything is written, so a manifest with a
typo'd requirement or a dependency cycle fails without having touched the
record. --dry-run stops after validation and prints the plan, which is how a
breakdown is checked before it is worth landing.

A Tasks manifest entry matching a delivery task that is already closed re-lands
onto that task. When the re-land changes its title or body, the task is
reopened and its `## Technical Plan` and `## Implementation` comments are
deleted, so it reads as needing a plan and an implementation again rather than
staying closed against a body nothing built; `hasImplementation` tracks the
attached pull request and is unaffected. A closed task the re-land leaves
byte-identical stays closed. Reopened task ids are listed in the evidence
comment and in the printed `reopened` array. --dry-run reports the closed tasks
the breakdown lands onto as `reopenCandidates`; which of them change, and so
which are reopened, is only known once the bodies are written.

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
from dataclasses import dataclass
from pathlib import Path


from pdlc.internal.workitem import (
    is_stage_skipped,
    item_gate,
    item_status,
    pipeline_for_item,
    post_comment,
    read_section,
    resolve_item,
    set_state,
    splice_section,
    state_for_item,
    subissues_for,
    upsert_tasks,
    write_body,
)
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, validate_attachments
from pdlc.internal.invalidation import reauthor_invalidate_stage, reopen_tasks
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import assert_unmarked, load_json_array, print_help, require_file, resolve_text, wants_help
from pdlc.domain.workflow import Event, Pipeline, State, decision_required_message

from pdlc.domain.task_plan import build_plan, declared_identifiers, resolve_task_ids, tagged_title
FR_C_PATTERN = re.compile(r"\b(?:FR|C)-[0-9]+\b")
UJ_PATTERN = re.compile(r"\bUJ-[0-9]+\b")
UI_HEADING_PATTERN = re.compile(r"^##[ \t]+UI[ \t]*$")
NO_UI_PATTERN = re.compile(r"no UI is required|UI is not required|UI not required", re.IGNORECASE)

@dataclass(frozen=True)
class PublicationContext:
    record: dict
    pipeline: Pipeline
    reauthor: bool = False


def land_ui(issue: str, item: str, parent_body: str, body_path: Path, evidence_body: str, dry_run: bool, attachment_inputs: list[dict], target: State, context: PublicationContext) -> None:
    lines = body_path.read_text(encoding="utf-8").splitlines()
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

    if context.reauthor:
        reauthor_invalidate_stage(context.record, "UI", context.pipeline)

    attachments = save_attachments(issue, attachment_inputs)
    spliced = splice_section(parent_body, "UI", fragment)
    write_body(str(issue), spliced)

    post_comment(issue, evidence_body, "UI")
    set_state(item, target.stage, target.gate.value, target.lifecycle.value)

    print(json.dumps({
        "published": True,
        "stage": "UI",
        "itemId": item,
        "work_item": int(issue),
        "journeys": journeys,
        "gateState": target.gate.value,
        "attachments": attachments,
    }))


def land_tasks(issue: str, item: str, manifest_path: Path, evidence_body: str | None, dry_run: bool, parent_body: str, attachment_inputs: list[dict], target: State, context: PublicationContext) -> None:
    manifest = load_json_array("--manifest", manifest_path, allow_empty=False)
    for index, task in enumerate(manifest, 1):
        if "id" in task and task.get("id") is not None and not isinstance(task.get("id"), str):
            raise PdlcError(f"manifest entry {index} id must be a string")

    for index, task in enumerate(manifest, 1):
        if "body" in task and task.get("body") is not None and not isinstance(task.get("body"), str):
            raise PdlcError(f"manifest entry {index} body must be a file path string")
        if not isinstance(task.get("title", ""), str):
            raise PdlcError(f"manifest entry {index} title must be a string")
        task["bodyText"] = require_file("task body file", task.get("body")).read_text(encoding="utf-8")

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

    # A closed task named by the breakdown is only actually reopened when this
    # call changes its title or body; the dry run cannot know that yet, so it
    # reports the candidates rather than a prediction.
    closed_in_breakdown = sorted(
        task["taskId"] for task in existing
        if task.get("taskId") and task["taskId"] in {t["id"] for t in plan["tasks"]} and task.get("state") == "CLOSED"
    )

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
            "reopenCandidates": closed_in_breakdown,
            "attachmentCount": len(attachment_inputs),
        }))
        return

    if context.reauthor:
        reauthor_invalidate_stage(context.record, "Tasks", context.pipeline)

    attachments = save_attachments(issue, attachment_inputs)
    results = upsert_tasks(issue, [
        {**task, "title": tagged_title(task)} for task in plan["tasks"]
    ], existing)

    created = [r["taskId"] for r in results if r["action"] == "created"]
    updated = [r["taskId"] for r in results if r["action"] == "updated"]
    retitled = [r["taskId"] for r in results if r["action"] == "retitled"]
    unchanged = [r["taskId"] for r in results if r["action"] == "unchanged"]
    open_orphans = [task["taskId"] for task in plan["orphans"] if task.get("state") != "CLOSED"]

    # A re-landed breakdown that rewrites a task Implementation already closed
    # invalidates that task's plan and implementation: without the reopen it
    # stays closed, so no later stage is eligible to build the new body and the
    # record reads as fully delivered against a breakdown nothing implemented.
    # Scoped to tasks this call actually rewrote — an `unchanged` closed task is
    # still faithfully implemented and stays closed. Targeting `Technical Plan`
    # retires the plan as well as the implementation, matching the Tasks stage's
    # own evidence dependencies.
    changed = [str(r["number"]) for r in results if r["action"] in ("updated", "retitled")]
    task_ids = {str(r["number"]): r["taskId"] for r in results}
    reopened: list[str] = []
    if changed:
        numbers = reopen_tasks(
            issue, "Technical Plan", changed,
            reason="Reopened for rework: the task body changed in a re-landed breakdown.",
        )
        reopened = [task_ids[number] for number in numbers]

    # The evidence body is the durable judgement. Counts, order, and coverage
    # are already recoverable from the task tree and should not inflate history.
    assert evidence_body is not None
    summary_lines = [evidence_body.rstrip("\n")]
    if open_orphans:
        summary_lines += ["", f"Exception: open tasks absent from this breakdown: {', '.join(open_orphans)}"]
    if reopened:
        summary_lines += ["", f"Reopened for rework, their plan and implementation retired: {', '.join(reopened)}"]

    post_comment(issue, "\n".join(summary_lines) + "\n", "TASKS")

    set_state(item, target.stage, target.gate.value, target.lifecycle.value)

    print(json.dumps({
        "published": True,
        "stage": "Tasks",
        "itemId": item,
        "work_item": int(issue),
        "gateState": target.gate.value,
        "created": created,
        "updated": updated,
        "retitled": retitled,
        "unchanged": unchanged,
        "orphans": open_orphans,
        "reopened": reopened,
        "order": plan["order"],
        "tasks": results,
        "attachments": attachments,
    }))


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

    parser = argparse.ArgumentParser(description="Land a pdlc-tasks stage")
    parser.add_argument("--work-item", required=True)
    parser.add_argument("--stage", required=True, choices=["UI", "Tasks"])
    parser.add_argument("--body")
    parser.add_argument("--manifest")
    parser.add_argument("--evidence")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(script_args)

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
        evidence_body: str | None = None
        if not args.dry_run:
            if not args.evidence:
                raise PdlcError("--evidence FILE|- is required")
            evidence_body = resolve_text(args.evidence, label="--evidence")
            assert_unmarked(evidence_body, "--evidence")

        # Guard the record's state
        #
        # The gate check is what stops a second authoring pass from posting
        # over an artifact that is already awaiting review or approval and
        # silently destroying a pending approval.
        record = resolve_item(args.work_item)
        pipeline = pipeline_for_item(record)
        item = record["id"]
        current_stage = item_status(record)
        gate = item_gate(record)

        if current_stage != args.stage:
            raise PdlcError(f"cannot land {args.stage}: the record is at {current_stage}")
        # Changes Required lands exactly like Stale: a resolved decision parks
        # the stage there, and the re-authored artifact publishes from it.
        if gate in ("Pending", "Stale", "Changes Required"):
            pass
        elif gate in ("Review Required", "Approval Required") and not args.dry_run:
            # Defer this mutation until the complete artifact has validated.
            # Invalid manifests must leave the published gate untouched.
            pass
        elif gate == "Review Required":
            pass
        elif gate == "Approval Required":
            raise PdlcError(f"{args.stage} is at {gate}; return it to Stale with pdlc post invalidate before re-authoring it")
        elif gate == "Decision Required":
            raise PdlcError(decision_required_message(args.stage))
        else:
            raise PdlcError(f"cannot land {args.stage} from Gate State: {gate or 'unset'}")
        if is_stage_skipped(record, args.stage):
            raise PdlcError(f"{args.stage} is declared in Skipped States; nothing to land")
        state = state_for_item(record, pipeline)
        # Reauthoring is validated against the existing record first, but its
        # publication transition is the same as publishing from Stale.
        reauthor = gate in ("Review Required", "Approval Required")
        if reauthor:
            state = pipeline.next_state(state, Event.REAUTHORED)
        try:
            target = pipeline.next_state(state, Event.PUBLISHED)
        except ValueError as error:
            raise PdlcError(str(error)) from None

        parent_body = record.get("issueBody") or ""

        if args.stage == "UI":
            context = PublicationContext(record, pipeline, reauthor and not args.dry_run)
            land_ui(args.work_item, item, parent_body, body_path, evidence_body, args.dry_run, attachment_inputs, target, context)
        else:
            context = PublicationContext(record, pipeline, reauthor and not args.dry_run)
            land_tasks(args.work_item, item, manifest_path, evidence_body, args.dry_run, parent_body, attachment_inputs, target, context)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
