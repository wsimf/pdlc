#!/usr/bin/env python3
"""NAME
    pdlc post tasks - land the UI or Tasks stage

USAGE
    - if landing the UI stage for a work item with a user-facing surface:
        pdlc post tasks --work-item N --stage UI    --body FILE     --evidence FILE|- [--dry-run] [--attachment PATH [--attachment-description TEXT]]
    - if landing the UI stage for a work item with no user-facing surface:
        pdlc post tasks --work-item N --stage UI    --body FILE --no-ui --evidence FILE|- [--dry-run] [--attachment PATH [--attachment-description TEXT]]
    - if landing the Tasks stage:
        pdlc post tasks --work-item N --stage Tasks --manifest FILE --evidence FILE|- [--dry-run] [--attachment PATH [--attachment-description TEXT]]
    - if correcting a landed UI or Tasks artifact while the record is at a later stage, add to either form:
        --patch [--impact FILE|-]

FLAGS
    --work-item N                        required; the work item's number
    --stage UI|Tasks                     required; which stage this call lands
    --body FILE                          required with --stage UI; the `## UI` section's content
    --no-ui                              action="store_true"; only valid with --stage UI; declares the work item
                                         has no user-facing surface, so --body names no UJ-N journey
    --manifest FILE                      required with --stage Tasks; JSON array of delivery tasks
    --evidence FILE|-                    required unless --dry-run; the review evidence body
    --dry-run                            validate and print the plan without landing it
    --patch                              action="store_true"; land onto the already-landed --stage artifact
                                         while the record stays on its later active stage
    --impact FILE|-                      only with --patch; the impact report whose
                                         `Earliest affected stage:` line reads `none` or an intermediate stage
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
For a non-dry-run Tasks publication, the command writes auto-assigned IDs back
to the manifest before its first remote write, so the same file identifies
partly created tasks on a retry.

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

With --patch, the artifact is landed onto a record whose active stage is
later than --stage and may patch it (see `pdlc guide patch`), and the record
stays on that stage. The landing and the stage's evidence comment are exactly
those of a normal land; a `PDLC-PATCHED` comment follows, opening with
`Patched stage: <stage>` and `Active stage: <stage> / <gate>` lines, then the
impact report (or `No intermediate stages.`). An active gate of Review
Required or Approval Required is reset to Stale, since the published artifact
was built on the old text; a work gate is left as is. Any other active gate is
refused, Decision Required with a pointer to `pdlc guide decisions`.
--impact is required when a non-skipped stage lies between --stage and the
active stage. Its verdict decides where the record goes: `none` keeps it on
the active stage; naming one of those intermediate stages lands the patch and
returns the record to that stage at Stale, adding a `Returned to: <stage> /
Stale` line to `PDLC-PATCHED` and posting a `PDLC-INVALIDATED` comment for that
stage with the impact report as its evidence; any other verdict is refused.
--dry-run additionally prints `impactRequired`, the intermediate stages, and,
given --impact, `returnedTo`.

A patch keeps the shape later stages were built on, and a change to it is
refused with a pointer to `pdlc post invalidate`: a UI patch keeps the landed
applicability (--no-ui or not) and, when --impact is required and its verdict
is `none`, the landed set of `UJ-*` ids; a Tasks patch names every landed task by `id`, adds and
removes none, and keeps each task's `ui`. Only titles and bodies change, and
`"unchanged": true` entries are allowed. A refusal writes nothing.

An existing task may be carried as `"action": "retain"`, with its generated
title, body file, type, coverage, dependencies, and baseline hash. The command
refuses a stale baseline, compares the returned content with the stored task,
and writes only changed tasks. A `"remove"` entry needs an existing id,
number, baseline, and reason; it closes and detaches an unimplemented task while
preserving its Issue history. A task with a registered PR cannot be removed.
Descoped task ids remain reserved for later breakdowns.
Legacy `"unchanged": true` entries remain accepted.

UI --body is the `## UI` section's content; a leading `## UI` heading is
tolerated and stripped. Applicability is explicit, and it is carried by the
flag rather than by the fragment's wording: without --no-ui the fragment must
name at least one `UJ-N` journey, and --no-ui declares there is no user-facing
surface and refuses a fragment that names one. --body is required either way —
a work item with no UI still records why, as a reviewable artifact. The printed
`uiRequired` reports which of the two landed.

Tasks --manifest is a JSON array, one entry per delivery task:

    [
      {
        "id": "TASK-001",              optional; assigned from the next free
                                       number when absent
        "title": "Persist route profile geometry",
                                       human-readable half only — the script
                                       composes the stable WORK-N-TASK-NNN
        "body": "/tmp/task-001.md",    the delivery task body
        "type": "core",                core or ui
        "covers": ["FR-2", "C-1"],     FR-*/C-*/UJ-* this task delivers
        "depends": [],                 tasks that must land first
        "action": "create"             create, retain, or remove
      }
    ]

`create` may omit `id`, and an entry with neither action nor id defaults to create; `retain` requires an existing id and generated
`baseline`, and keeps all editable fields above. `remove` requires id,
number, action, baseline, and a nonempty reason. The printed `removed` array names
descoped tasks. --dry-run lists them before any write.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


from pdlc.internal.workitem import (
    comments_for_issue,
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
    remove_task,
    tasks_by_number,
    upsert_tasks,
    write_body,
)
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, validate_attachments
from pdlc.internal.invalidation import land_patch, reauthor_invalidate_stage, record_patch_plan, reopen_tasks
from pdlc.domain.model import UI_TAG, marked_comments, task_title
from pdlc.domain.patch import PatchPlan, require_same_ids
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.task_artifact import snapshot, stored_fields
from pdlc.internal.inputs import assert_unmarked, load_json_array, print_help, require_file, resolve_text, wants_help
from pdlc.domain.workflow import Event, Pipeline, State, decision_required_message

from pdlc.domain.task_plan import (
    JOURNEY_ID_PATTERN,
    REQUIREMENT_ID_PATTERN,
    build_plan,
    declared_identifiers,
    resolve_task_ids,
    tagged_title,
)
from pdlc.internal.failure import Recovery, report_failure, set_recovery
UI_HEADING_PATTERN = re.compile(r"^##[ \t]+UI[ \t]*$")
_DESCOPED_LINE = re.compile(r"^Descoped tasks: (.*)$", re.MULTILINE)
_TASK_ID = re.compile(r"\bTASK-[0-9]{3}\b")

@dataclass(frozen=True)
class PublicationContext:
    record: dict
    pipeline: Pipeline
    reauthor: bool = False
    # Set under --patch: the record lands on `patch.target` (the active stage,
    # or the stage the impact report returned it to) through `land_patch`
    # instead of this stage's own publish transition.
    patch: PatchPlan | None = None
    impact: str | None = None


def _patch_summary(plan: PatchPlan) -> dict:
    return {
        "patched": plan.patched_stage,
        "activeStage": plan.source.stage,
        "impactRequired": plan.impact_required,
        "intermediateStages": list(plan.intermediate),
        "returnedTo": plan.rewind,
        "status": plan.target.stage,
    }


def _check_ui_patch(context: PublicationContext, parent_body: str, journeys: list[str], no_ui: bool) -> None:
    assert context.patch is not None
    landed = declared_identifiers(read_section(parent_body, "UI"), JOURNEY_ID_PATTERN)
    if no_ui != (not landed):
        raise PdlcError(
            "a patch must keep the landed UI applicability; "
            "return UI to Stale with `pdlc post invalidate` to change it"
        )
    # A rewind re-runs the task breakdown, which re-checks its coverage.
    if context.patch.impact_required and context.patch.rewind is None:
        require_same_ids("journey", landed, journeys, "Tasks")


def _check_tasks_patch(manifest: list[dict], existing: list[dict]) -> None:
    landed = {task["taskId"]: task for task in existing if task.get("taskId")}
    missing_ids = [index for index, task in enumerate(manifest, 1) if not task.get("id")]
    if missing_ids:
        raise PdlcError(f"a patch must name every task by id; manifest entry {missing_ids[0]} has none")
    require_same_ids("task", sorted(landed), [task["id"] for task in manifest], "Tasks")
    for task in manifest:
        if task.get("ui") is not task_title(landed[task["id"]]).startswith(UI_TAG):
            raise PdlcError(
                f"a patch must keep each task's ui flag, but {task['id']} changes it; "
                "return Tasks to Stale with `pdlc post invalidate` instead"
            )


def land_ui(issue: str, item: str, parent_body: str, body_path: Path, evidence_body: str, dry_run: bool, attachment_inputs: list[dict], target: State, context: PublicationContext, no_ui: bool) -> None:
    lines = body_path.read_text(encoding="utf-8").splitlines()
    if lines and UI_HEADING_PATTERN.match(lines[0]):
        lines = lines[1:]
    fragment = "\n".join(lines)
    if not fragment.strip():
        raise PdlcError(f"--body file holds nothing but its heading: {body_path}")

    journeys = declared_identifiers(fragment, JOURNEY_ID_PATTERN)

    # Applicability is carried by the flag, never by the fragment's wording.
    # Sniffing prose for a "no UI" sentence made the caller guess phrasings,
    # so --body owns the reviewable rationale and --no-ui owns the decision.
    if no_ui and journeys:
        raise PdlcError(
            "--no-ui declares no user-facing surface, but --body names "
            f"{', '.join(journeys)}; drop --no-ui, or remove the journeys"
        )
    if not no_ui and not journeys:
        raise PdlcError(
            "--body names no UJ-N journey; name at least one, "
            "or pass --no-ui if this work item has no user-facing surface"
        )

    if context.patch is not None:
        _check_ui_patch(context, parent_body, journeys, no_ui)

    if dry_run:
        print(json.dumps({
            "dryRun": True, "stage": "UI", "uiRequired": not no_ui, "journeys": journeys,
            "attachmentCount": len(attachment_inputs),
            **(_patch_summary(context.patch) if context.patch else {}),
        }))
        return

    if context.reauthor:
        reauthor_invalidate_stage(context.record, "UI", context.pipeline)

    attachments = save_attachments(issue, attachment_inputs)
    spliced = splice_section(parent_body, "UI", fragment)
    write_body(str(issue), spliced)

    post_comment(issue, evidence_body, "UI")
    if context.patch is not None:
        land_patch(issue, context.record, context.patch, context.impact)
        target = context.patch.target
    else:
        set_state(item, target.stage, target.gate.value, target.lifecycle.value)

    print(json.dumps({
        "published": True,
        "stage": "UI",
        "itemId": item,
        "work_item": int(issue),
        "uiRequired": not no_ui,
        "journeys": journeys,
        "gateState": target.gate.value,
        "attachments": attachments,
        **(_patch_summary(context.patch) if context.patch else {}),
    }))


def _descope_ids(issue: str) -> set[str]:
    """Removed task identities stay reserved across later breakdown passes."""
    ids: set[str] = set()
    for comment in marked_comments(comments_for_issue(issue)):
        if comment["marker"] != "TASKS":
            continue
        for match in _DESCOPED_LINE.finditer(comment["body"]):
            ids.update(_TASK_ID.findall(match.group(1)))
    return ids


def _prepare_task_manifest(manifest: list[dict], existing: list[dict], issue: str, reserved: set[str]) -> tuple[list[dict], list[dict]]:
    """Resolve editable planner entries to the established task-plan shape."""
    by_id = {task["taskId"]: task for task in existing if task.get("taskId")}
    prepared: list[dict] = []
    removals: list[dict] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(manifest, 1):
        if isinstance(entry.get("id"), str):
            if entry["id"] in seen_ids:
                raise PdlcError(f"duplicate task id: {entry['id']}")
            seen_ids.add(entry["id"])
        action = entry.get("action")
        if action is None:
            if "type" in entry:
                action = "create" if not entry.get("id") else None
            else:
                prepared.append(dict(entry))
                continue
        if action not in ("create", "retain", "remove"):
            raise PdlcError(f"manifest entry {index} action must be create, retain, or remove")
        task_id = entry.get("id")
        if action == "create":
            if task_id in reserved:
                raise PdlcError(f"{task_id} was descoped; use a new id")
        else:
            if action == "remove" and isinstance(task_id, str) and task_id not in by_id:
                number = entry.get("number")
                if isinstance(number, int) and number > 0:
                    [detached] = tasks_by_number([str(number)])
                    reason = entry.get("reason")
                    note = f"Descoped from work item #{issue}: {reason}"
                    if (detached.get("taskId") == task_id and detached.get("state") == "CLOSED"
                            and isinstance(reason, str) and any(note in comment for comment in detached.get("comments", []))):
                        by_id[task_id] = detached
                        already_removed = True
                    else:
                        already_removed = False
                else:
                    already_removed = False
            else:
                already_removed = False
            if not isinstance(task_id, str) or task_id not in by_id:
                raise PdlcError(f"manifest entry {index} must name an existing task for {action}")
            baseline = entry.get("baseline")
            if action == "remove" and (not isinstance(baseline, str) or baseline != snapshot(stored_fields(by_id[task_id]))):
                raise PdlcError(f"{task_id} changed since its planner artifact was generated; regenerate it")
        if action == "remove":
            reason = entry.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise PdlcError(f"{task_id} removal requires a reason")
            if entry.get("number") != by_id[task_id]["number"]:
                raise PdlcError(f"{task_id} removal requires its generated task number")
            if by_id[task_id].get("prs"):
                raise PdlcError(f"{task_id} has completed work or a registered pull request; resolve it before removal")
            if any(key in entry for key in ("title", "body", "type", "covers", "depends", "ui")):
                raise PdlcError(f"{task_id} removal must contain only id, number, action, baseline, and reason")
            removals.append({"id": task_id, "number": by_id[task_id]["number"], "reason": reason.strip(), "already_removed": already_removed})
            continue
        kind = entry.get("type")
        if kind not in ("core", "ui"):
            raise PdlcError(f"manifest entry {index} type must be core or ui")
        body_path = entry.get("body")
        if not isinstance(body_path, str):
            raise PdlcError(f"manifest entry {index} body must be a file path string")
        body_text = require_file("task body file", body_path).read_text(encoding="utf-8")
        task = {
            "id": task_id, "title": entry.get("title"), "body": body_path,
            "bodyText": body_text, "ui": kind == "ui",
            "covers": entry.get("covers"), "depends": entry.get("depends") or [],
        }
        body_fields = stored_fields({"body": body_text})
        if (task["covers"], task["depends"]) != (body_fields["covers"], body_fields["depends"]):
            raise PdlcError(f"manifest entry {index} covers and depends must match its task body")
        after = {"title": task["title"], "type": kind, "covers": task["covers"],
                 "depends": task["depends"], "body": body_text}
        if action == "retain" or task_id in by_id:
            before = stored_fields(by_id[task_id])
            already_applied = action == "retain" and entry.get("baseline") != snapshot(before)
            if already_applied and after != before:
                raise PdlcError(f"{task_id} changed since its planner artifact was generated; regenerate it")
            if action == "create" and after != before:
                raise PdlcError(f"{task_id} already exists with different content; use a new id")
            if after == before:
                if already_applied and by_id[task_id].get("state") == "CLOSED":
                    task["recoveryReopen"] = True
                task["unchanged"] = True
                task.pop("title")
                task.pop("body")
                task.pop("bodyText")
        prepared.append(task)
    return prepared, removals


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
        if "unchanged" in task and not isinstance(task["unchanged"], bool):
            raise PdlcError(f"manifest entry {index} unchanged must be true or false")
        if task.get("unchanged") is True:
            if task.get("body") is not None:
                raise PdlcError(f"manifest entry {index} is marked \"unchanged\" and cannot also set a body")
            continue
        if task.get("action") is None and "type" not in task:
            task["bodyText"] = require_file("task body file", task.get("body")).read_text(encoding="utf-8")

    existing = subissues_for(issue)
    reserved_ids = _descope_ids(issue)
    explicit_actions = any("action" in entry or "type" in entry for entry in manifest)
    source_manifest = manifest
    manifest, removals = _prepare_task_manifest(source_manifest, existing, issue, reserved_ids)
    if not manifest:
        raise PdlcError("a Tasks breakdown must retain or create at least one task")
    existing_ids = [task["taskId"] for task in existing if task.get("taskId")] + sorted(reserved_ids)
    if context.patch is not None:
        if removals:
            raise PdlcError("a Tasks patch cannot remove tasks; return Tasks to Stale")
        _check_tasks_patch(manifest, existing)

    requirements = declared_identifiers(read_section(parent_body, "Product"), REQUIREMENT_ID_PATTERN)
    journeys = declared_identifiers(read_section(parent_body, "UI"), JOURNEY_ID_PATTERN)

    resolved = resolve_task_ids(manifest, existing_ids)
    plan = build_plan(resolved, [task for task in existing if task.get("taskId") not in {r["id"] for r in removals}], requirements, journeys)

    if plan["errors"]:
        print("pdlc: the task breakdown does not satisfy the parent record:", file=sys.stderr)
        for error in plan["errors"]:
            print(f"  - {error}", file=sys.stderr)
        raise SystemExit(1)
    if explicit_actions and plan["orphans"]:
        names = ", ".join(task["taskId"] for task in plan["orphans"])
        raise PdlcError(f"existing tasks missing from the manifest: {names}; retain or remove each explicitly")

    # A closed task named by the breakdown is only actually reopened when this
    # call changes its title or body; the dry run cannot know that yet, so it
    # reports the candidates rather than a prediction.
    carried_ids = {task["id"] for task in plan["tasks"] if task.get("unchanged")}
    writable = [task for task in plan["tasks"] if not task.get("unchanged")]
    reopen_candidate_ids = {task["id"] for task in writable}
    reopen_candidate_ids.update(task["id"] for task in plan["tasks"] if task.get("recoveryReopen"))
    closed_in_breakdown = sorted(
        task["taskId"] for task in existing
        if task.get("taskId") in reopen_candidate_ids and task.get("state") == "CLOSED"
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
                    "unchanged": bool(task.get("unchanged")),
                }
                for task in plan["tasks"]
            ],
            "order": plan["order"],
            "orphans": [task["taskId"] for task in plan["orphans"]],
            "removed": [task["id"] for task in removals],
            "reopenCandidates": closed_in_breakdown,
            "attachmentCount": len(attachment_inputs),
            **(_patch_summary(context.patch) if context.patch else {}),
        }))
        return

    # Fix auto-assigned identities in the local artifact before a remote create.
    # A partial publication can then use this same manifest for recovery.
    active_entries = [entry for entry in source_manifest if entry.get("action") != "remove"]
    if any(not entry.get("id") for entry in active_entries):
        for entry, task in zip(active_entries, resolved, strict=True):
            if not entry.get("id"):
                entry["id"] = task["id"]
                if "type" in entry:
                    entry["action"] = "create"
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=".tasks-", suffix=".json", dir=manifest_path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(source_manifest, handle, indent=2)
                    handle.write("\n")
                os.replace(temporary, manifest_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        except OSError as error:
            raise PdlcError(f"cannot save assigned task ids in {manifest_path}: {error}") from error

    if context.reauthor:
        reauthor_invalidate_stage(context.record, "Tasks", context.pipeline)

    attachments = save_attachments(issue, attachment_inputs)
    results = upsert_tasks(issue, [
        {**task, "title": tagged_title(task)} for task in writable
    ], existing)
    # A carried task is never handed to the backend, so it cannot be rewritten,
    # retitled, or reopened by this call; it is still reported, because the
    # breakdown declares it and its coverage counts.
    existing_by_id = {task["taskId"]: task for task in existing if task.get("taskId")}
    results += [
        {
            "action": "unchanged",
            "taskId": task_id,
            "number": existing_by_id[task_id]["number"],
            "title": existing_by_id[task_id]["title"],
            "url": existing_by_id[task_id].get("url", ""),
        }
        for task_id in sorted(carried_ids)
    ]

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
    changed += [str(existing_by_id[task["id"]]["number"]) for task in plan["tasks"] if task.get("recoveryReopen")]
    task_ids = {str(r["number"]): r["taskId"] for r in results}
    reopened: list[str] = []
    if changed:
        numbers = reopen_tasks(
            issue, "Technical Plan", changed,
            reason="Reopened for rework: the task body changed in a re-landed breakdown.",
        )
        reopened = [task_ids[number] for number in numbers]

    for removal in removals:
        if removal["already_removed"]:
            continue
        post_comment(str(removal["number"]), f"Descoped from work item #{issue}: {removal['reason']}\n", "TASKS")
        remove_task(issue, str(removal["number"]))

    # The evidence body is the durable judgement. Counts, order, and coverage
    # are already recoverable from the task tree and should not inflate history.
    assert evidence_body is not None
    summary_lines = [evidence_body.rstrip("\n")]
    if open_orphans:
        summary_lines += ["", f"Exception: open tasks absent from this breakdown: {', '.join(open_orphans)}"]
    if reopened:
        summary_lines += ["", f"Reopened for rework, their plan and implementation retired: {', '.join(reopened)}"]
    if removals:
        summary_lines += ["", "Descoped tasks: " + ", ".join(f"{task['id']} ({task['reason']})" for task in removals)]

    post_comment(issue, "\n".join(summary_lines) + "\n", "TASKS")

    if context.patch is not None:
        land_patch(issue, context.record, context.patch, context.impact)
        target = context.patch.target
    else:
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
        "removed": [task["id"] for task in removals],
        "order": plan["order"],
        "tasks": results,
        "attachments": attachments,
        **(_patch_summary(context.patch) if context.patch else {}),
    }))


def _recovery(issue: str, stage: str, patch: bool) -> Recovery:
    """How to check a failed landing; the Tasks stage also has to reopen any
    rewritten task a failed run left closed, which a re-run never does."""
    marker = "UI" if stage == "UI" else "TASKS"
    if patch:
        return Recovery(
            check=f"pdlc inspect timeline {issue}",
            landed=f"PDLC-PATCHED is newer than this PDLC-{marker} evidence and `pdlc inspect {issue}` shows the stage and gate the dry run reported",
            otherwise="run the same command with --dry-run and, only if it still reports the same plan, re-run: {rerun}",
            note="If the record already moved to the returned stage, do not re-run; stop and report to the driver any task still closed, which needs `pdlc post invalidate` for that task.",
        )
    note = f"A re-run after the PDLC-{marker} evidence landed posts a second one; mention it in your report."
    if stage == "Tasks":
        note += (
            " After it succeeds, inspect each rewritten task for a closed state or stale plan/implementation evidence,"
            " and each removed task for a closed state and absence from the parent's active task list."
            " Report any incomplete task recovery to the driver with the task inspection output."
        )
    return Recovery(
        check=f"pdlc inspect {issue}",
        landed=f"the gate is Review Required and `pdlc inspect timeline {issue}` shows this PDLC-{marker} evidence as the newest",
        note=note,
    )


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

    parser = argparse.ArgumentParser(description="Land a pdlc-tasks stage")
    parser.add_argument("--work-item", required=True)
    parser.add_argument("--stage", required=True, choices=["UI", "Tasks"])
    parser.add_argument("--body")
    parser.add_argument("--manifest")
    parser.add_argument("--evidence")
    parser.add_argument("--no-ui", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--patch", action="store_true")
    parser.add_argument("--impact")
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
            if args.no_ui:
                raise PdlcError("--no-ui is only valid with --stage UI")
            manifest_path = require_file("--manifest file", args.manifest)

        if args.impact and not args.patch:
            raise PdlcError("--impact is only valid with --patch")
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
        parent_body = record.get("issueBody") or ""

        set_recovery(_recovery(args.work_item, args.stage, args.patch))
        if args.patch:
            impact = resolve_text(args.impact, label="--impact") if args.impact else None
            plan = record_patch_plan(record, args.stage, impact, args.dry_run)
            context = PublicationContext(record, pipeline, patch=plan, impact=impact)
            if args.stage == "UI":
                land_ui(args.work_item, item, parent_body, body_path, evidence_body, args.dry_run, attachment_inputs, plan.target, context, args.no_ui)
            else:
                land_tasks(args.work_item, item, manifest_path, evidence_body, args.dry_run, parent_body, attachment_inputs, plan.target, context)
            return 0

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

        if args.stage == "UI":
            context = PublicationContext(record, pipeline, reauthor and not args.dry_run)
            land_ui(args.work_item, item, parent_body, body_path, evidence_body, args.dry_run, attachment_inputs, target, context, args.no_ui)
        else:
            context = PublicationContext(record, pipeline, reauthor and not args.dry_run)
            land_tasks(args.work_item, item, manifest_path, evidence_body, args.dry_run, parent_body, attachment_inputs, target, context)
    except PdlcError as error:
        return report_failure(error)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
