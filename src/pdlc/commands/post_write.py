#!/usr/bin/env python3
"""NAME
    pdlc post write - publish the reviewed Product artifact

USAGE
    - if creating a new record:
        pdlc post write --title TITLE --slug SLUG --evidence FILE|- --body FILE [--attachment PATH [--attachment-description TEXT]]
    - if updating an existing record's Product section:
        pdlc post write --work-item WORK_ITEM --evidence FILE|- --body FILE [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --title TITLE                       required when creating a new record
    --slug SLUG                         required when creating a new record
    --work-item WORK_ITEM               required when updating an existing record
    --evidence FILE|-                   required; the review evidence body
    --body FILE                         required; the Product/Decisions/Open Questions content
    --attachment PATH (repeatable)      attach a local file's contents to the evidence comment
    --attachment-description TEXT       description for the --attachment immediately before it

DESCRIPTION
    Publishes the Product artifact: creates a new record, or replaces an
existing record's Product section in one body edit while preserving
sections owned by later stages.

The supplied body contains exactly the three sections owned by Product:
`Product`, `Decisions`, and `Open Questions`. New records use it as their
initial body.

An existing record lands from `Product / Pending`, `Changes Required`, or
`Stale`. A record at `Product / Review Required` (published without its local
review) or `Product / Approval Required` (a driver change request) is
re-authored in place: the script resets Product to Stale itself (no comment —
the spec never settled at Approved, and the re-land's own Product evidence
records the change) and re-lands the reviewed spec in the same call. Decision
Required is refused with a pointer to `pdlc guide decisions`; any other gate
is refused.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


from pdlc.internal.workitem import (
    create_work_item,
    item_gate,
    item_status,
    pipeline_for_item,
    post_comment,
    read_section,
    resolve_item,
    set_slug,
    set_state,
    state_for_item,
    update_sections,
)
from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, validate_attachments, work_item_number
from pdlc.internal.invalidation import reauthor_invalidate_stage
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help, require_file, resolve_text, wants_help
from pdlc.domain.stages import Gate
from pdlc.domain.workflow import Event, State, WorkType, decision_required_message
from pdlc.domain.workflows.workflow_feature import FEATURE_PIPELINE

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
OWNED_SECTIONS = ("Product", "Decisions", "Open Questions")


def product_fragments(body_path: Path) -> dict[str, str]:
    body = body_path.read_text(encoding="utf-8")
    headings = level_two_headings(body)
    if not body.startswith("## Product") or headings != list(OWNED_SECTIONS):
        expected = ", ".join(f"## {section}" for section in OWNED_SECTIONS)
        actual = ", ".join(f"## {section}" for section in headings) or "none"
        raise PdlcError(f"--body must contain only {expected}, in that order; found {actual}")
    return {section: read_section(body, section).rstrip() for section in OWNED_SECTIONS}


def level_two_headings(body: str) -> list[str]:
    headings: list[str] = []
    fenced = False
    for line in body.splitlines():
        if line.startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            headings.append(line[3:].rstrip(" \t"))
    return headings


def publish_existing(issue: str, fragments: dict[str, str], evidence_body: str, attachment_inputs: list[dict]) -> dict:
    record = resolve_item(issue)
    pipeline = pipeline_for_item(record)
    if item_status(record) != "Product":
        raise PdlcError(f"cannot author Product while the record is at {item_status(record) or 'an unset stage'}")
    gate = item_gate(record)
    if gate in ("Review Required", "Approval Required"):
        # A published spec awaiting review or approval is re-landed in place:
        # reset Product to Stale ourselves and publish the reviewed spec in
        # this same call.
        reauthor_invalidate_stage(record, "Product", pipeline)
    elif gate == "Decision Required":
        raise PdlcError(decision_required_message("Product"))
    elif gate not in ("Pending", "Changes Required", "Stale"):
        raise PdlcError(
            f"Product is at {gate or 'an unset Gate State'}; "
            "return it to Stale with pdlc post invalidate before re-authoring"
        )
    state = state_for_item(record, pipeline)
    try:
        target = pipeline.next_state(state, Event.PUBLISHED)
    except ValueError as error:
        raise PdlcError(str(error)) from None
    headings = level_two_headings(record.get("issueBody") or "")
    duplicates = [section for section in OWNED_SECTIONS if headings.count(section) > 1]
    if duplicates:
        raise PdlcError(f"existing work item has duplicate Product-owned sections: {', '.join(duplicates)}")

    item_id = record["id"]
    attachments = save_attachments(work_item_number(record), attachment_inputs)
    update_sections(issue, fragments)
    post_comment(issue, evidence_body, "PRODUCT")
    set_state(item_id, target.stage, target.gate.value, target.lifecycle.value)
    return {
        "created": False,
        "itemId": item_id,
        "work_item_number": int(issue),
        "status": "Product",
        "gateState": target.gate.value,
        "attachments": attachments,
    }


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

    parser = argparse.ArgumentParser(description="Publish a reviewed PDLC Product artifact")
    parser.add_argument("--title")
    parser.add_argument("--slug")
    parser.add_argument("--work-item")
    parser.add_argument("--evidence", required=True, dest="evidence_file")
    parser.add_argument("--body", required=True, dest="body_file")
    args = parser.parse_args(script_args)

    try:
        is_new = args.work_item is None
        if is_new and (not args.title or not args.slug):
            raise PdlcError("--title and --slug are required when creating a new work item")
        if not is_new and (args.title or args.slug):
            raise PdlcError("--title and --slug are only valid when creating a new work item")
        if not is_new and not args.work_item.isdigit():
            raise PdlcError(f"--work-item must be an exact work item number: {args.work_item}")
        if is_new and not SLUG_PATTERN.match(args.slug):
            raise PdlcError(f"slug must be lowercase kebab-case: {args.slug}")

        evidence_body = resolve_text(args.evidence_file, label="--evidence")
        body_path = require_file("--body file", args.body_file)
        fragments = product_fragments(body_path)
        validate_attachments(attachment_inputs)

        if not is_new:
            result = publish_existing(args.work_item, fragments, evidence_body, attachment_inputs)
            print(json.dumps(result))
            return 0

        new_item = create_work_item(args.title, body_path.read_text(encoding="utf-8"), args.slug, WorkType.FEATURE)
        work_item_url = new_item["url"]
        work_item_number = str(new_item["number"])
        item_id = new_item["id"]

        attachments = save_attachments(work_item_number, attachment_inputs)
        target = FEATURE_PIPELINE.next_state(State("Product", Gate.PENDING), Event.PUBLISHED)
        set_state(item_id, target.stage, target.gate.value, target.lifecycle.value)
        set_slug(item_id, args.slug)
        post_comment(work_item_number, evidence_body, "PRODUCT")
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps({
        "created": True,
        "url": work_item_url,
        "itemId": item_id,
        "work_item_number": int(work_item_number),
        "status": target.stage,
        "gateState": target.gate.value,
        "attachments": attachments,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
