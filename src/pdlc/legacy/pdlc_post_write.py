#!/usr/bin/env python3
"""Publishes the reviewed Product artifact for a new or existing PDLC record.

    pdlc-post-write.py --title TITLE --slug SLUG --evidence FILE|- --body FILE [--attachment PATH [--attachment-description TEXT]]
    pdlc-post-write.py --work-item WORK_ITEM --evidence FILE|- --body FILE [--attachment PATH [--attachment-description TEXT]]

The supplied body contains exactly the three sections owned by Product:
`Product`, `Decisions`, and `Open Questions`. New records use it as their
initial body. Existing records replace those sections in one body edit while
preserving sections owned by later stages.

An existing record already at `Product / Approval Required` is re-authored in
place: the script resets Product to Stale itself (no comment — the spec never
settled at Approved, and the re-land's own Product evidence records the change)
and re-lands the reviewed spec in the same call.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


from pdlc.workitem import (  # type: ignore
    create_work_item,
    item_gate,
    item_status,
    post_comment,
    read_section,
    resolve_item,
    set_slug,
    set_state,
    update_sections,
)
from pdlc.attachments import parse_attachment_arguments, save_attachments, validate_attachments, work_item_number  # type: ignore
from pdlc.invalidation import reauthor_invalidate_stage  # type: ignore
from pdlc.pdlc_common import PdlcError, evidence_source, print_help, require_file, wants_help  # type: ignore

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
OWNED_SECTIONS = ("Product", "Decisions", "Open Questions")


def product_fragments(body_path: Path) -> dict[str, str]:
    body = body_path.read_text()
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


def publish_existing(issue: str, fragments: dict[str, str], evidence_path: Path, attachment_inputs: list[dict]) -> dict:
    record = resolve_item(issue)
    if item_status(record) != "Product":
        raise PdlcError(f"cannot author Product while the record is at {item_status(record) or 'an unset stage'}")
    gate = item_gate(record)
    if gate == "Approval Required":
        # The driver asked for a change before approving: reset Product to Stale
        # ourselves and re-land the reviewed spec in this same call.
        reauthor_invalidate_stage(record, "Product")
    elif gate not in ("Pending", "Changes Required", "Stale"):
        raise PdlcError(
            f"Product is at {gate or 'an unset Gate State'}; "
            "return it to Stale with pdlc-post-invalidate.py before re-authoring"
        )
    headings = level_two_headings(record.get("issueBody") or "")
    duplicates = [section for section in OWNED_SECTIONS if headings.count(section) > 1]
    if duplicates:
        raise PdlcError(f"existing work item has duplicate Product-owned sections: {', '.join(duplicates)}")

    item_id = record["id"]
    attachments = save_attachments(work_item_number(record), attachment_inputs)
    update_sections(issue, fragments)
    post_comment(issue, str(evidence_path), "PRODUCT")
    set_state(item_id, "Product", "Approval Required", "Planning")
    return {
        "created": False,
        "itemId": item_id,
        "work_item_number": int(issue),
        "status": "Product",
        "gateState": "Approval Required",
        "attachments": attachments,
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

        evidence_path, is_temporary = evidence_source("--evidence", args.evidence_file)
        try:
            body_path = require_file("--body file", args.body_file)
            fragments = product_fragments(body_path)
            validate_attachments(attachment_inputs)

            if not is_new:
                result = publish_existing(args.work_item, fragments, evidence_path, attachment_inputs)
                print(json.dumps(result))
                return 0

            new_item = create_work_item(args.title, body_path.read_text(), args.slug)
            work_item_url = new_item["url"]
            work_item_number = str(new_item["number"])
            item_id = new_item["id"]

            attachments = save_attachments(work_item_number, attachment_inputs)
            set_state(item_id, "Product", "Approval Required", "Planning")
            set_slug(item_id, args.slug)
            post_comment(work_item_number, str(evidence_path), "PRODUCT")
        finally:
            if is_temporary:
                evidence_path.unlink(missing_ok=True)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps({
        "created": True,
        "url": work_item_url,
        "itemId": item_id,
        "work_item_number": int(work_item_number),
        "status": "Product",
        "gateState": "Approval Required",
        "attachments": attachments,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
