#!/usr/bin/env python3
"""NAME
    pdlc post decision - close a Decision Required gate from a resolution manifest

USAGE
    pdlc post decision WORK_ITEM --manifest FILE [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --manifest FILE                     required; JSON array of decision resolutions, see below
    --attachment PATH (repeatable)      attach a local file's contents to the resolution comment
    --attachment-description TEXT       description for the --attachment immediately before it

DESCRIPTION
    Closes out a `Decision Required` gate in one call, once the driver has
    settled every open decision the reviewer raised.

Driver-only, like pdlc post approve / pdlc post invalidate: the scripts carry no
identity check, so only the orchestrator runs this, and only on an explicit
human instruction naming the record in this turn.

The manifest is a JSON array, one entry per open `## Decision Required` block.
Each entry is either answered or deferred:

    [
      { "decision": "On-device vs server-side snapping",
        "answer": "On-device",
        "rationale": "offline-first; a server round-trip breaks the core journey",
        "affects": "TASK-004" },

      { "decision": "Tile-pin quota ceiling",
        "defer": { "title": "Tile pin quota", "slug": "tile-pin-quota",
                   "body": "/tmp/pdlc-deferred-quota.md" } }
    ]

Each `defer` becomes its own PDLC work item at `Product / Pending` (resolved by
slug first, so a re-run after a mid-way failure reuses it rather than
double-creating), linked back to the origin with an Open Questions pointer. A
single `PDLC-RESOLUTION` comment, opening with a `Resolved stage: <stage>` line,
records every outcome, and the gate moves to
`Changes Required` — the stage's owner then reconciles against it with a
deferred point now out of scope (Implementation and Testing re-publish for a
fresh independent review; Verification re-runs its audit).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number
from pdlc.domain.lifecycle import NotFound, PdlcError
from pdlc.internal.inputs import load_json_array, print_help, require_file, wants_help
from pdlc.domain.stages import Gate
from pdlc.domain.workflow import Event, Lifecycle, WorkType
from pdlc.domain.workflows.workflow_feature import FEATURE_PIPELINE
from pdlc.internal.workitem import (
    append_to_section,
    create_work_item,
    find_marked_comments,
    item_for_issue,
    item_gate,
    post_comment,
    resolve_item,
    set_gate,
    set_slug,
    set_state,
    workflow_for_item,
)

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
def _validate(entries: list[dict]) -> None:
    if not entries:
        raise PdlcError("the manifest is empty — list one entry per open decision")
    for index, entry in enumerate(entries, start=1):
        where = f"manifest entry {index}"
        if not (entry.get("decision") or "").strip():
            raise PdlcError(f"{where}: 'decision' (the decision label) is required")
        answered = "answer" in entry
        deferred = "defer" in entry
        if answered == deferred:
            raise PdlcError(f"{where}: give exactly one of 'answer' or 'defer'")
        if answered:
            if not (entry.get("answer") or "").strip():
                raise PdlcError(f"{where}: 'answer' must not be empty")
            if not (entry.get("rationale") or "").strip():
                raise PdlcError(f"{where}: an answered decision needs a 'rationale'")
        else:
            defer = entry["defer"]
            if not isinstance(defer, dict):
                raise PdlcError(f"{where}: 'defer' must be an object with title, slug, body")
            if not (defer.get("title") or "").strip():
                raise PdlcError(f"{where}: 'defer.title' is required")
            if not SLUG_PATTERN.match(defer.get("slug") or ""):
                raise PdlcError(f"{where}: 'defer.slug' must be lowercase kebab-case")
            require_file(f"{where}: defer.body", defer.get("body"))


# Reuse an existing deferred record by slug, else create it at Product / Pending
# and point the origin's Open Questions at it.
def _defer(origin: str, stage: str, defer: dict) -> dict:
    title, slug = defer["title"].strip(), defer["slug"]
    try:
        existing = resolve_item(slug)
        return {"number": int(existing["content"]["number"]), "title": title, "reused": True}
    except NotFound:
        pass

    child = create_work_item(title, Path(defer["body"]).read_text(encoding="utf-8"), slug, WorkType.FEATURE)
    number = int(child["number"])
    initial_stage = FEATURE_PIPELINE.active_stage_names[0]
    set_state(child["id"], initial_stage, Gate.PENDING.value, Lifecycle.PLANNING.value)
    set_slug(child["id"], slug)
    post_comment(
        str(number),
        f"Split out of #{origin} during {stage} review to be settled independently. "
        f"See the PDLC-DECISION comment on #{origin} for the reviewer's question, options, and recommendation.",
    )
    append_to_section(origin, "Open Questions", [f"Deferred — {title}; tracked as #{number}."])
    return {"number": number, "title": title, "reused": False}


# The leading `Resolved stage:` line attributes the resolution to its stage for
# `pdlc inspect changes`.
def _resolution_body(stage: str, entries: list[dict], deferred: dict[int, dict]) -> str:
    blocks = [f"Resolved stage: {stage}"]
    for index, entry in enumerate(entries, start=1):
        lines = [f"### {entry['decision'].strip()}"]
        if "answer" in entry:
            lines.append(f"Decision: {entry['answer'].strip()}")
            lines.append(f"Rationale: {entry['rationale'].strip()}")
            if (entry.get("affects") or "").strip():
                lines.append(f"Affects: {entry['affects'].strip()}")
        else:
            child = deferred[index]
            lines.append(f"Deferred to #{child['number']} — {child['title']}.")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def post_decision(issue: str, manifest_path: Path, attachment_inputs: list[dict]) -> dict:
    record = item_for_issue(issue)
    pipeline, state = workflow_for_item(record)
    if item_gate(record) != "Decision Required":
        raise PdlcError(f"post-decision requires Gate State = Decision Required, not {item_gate(record) or 'unset'}")
    stage = state.stage
    try:
        target = pipeline.next_state(state, Event.DECISION_RESOLVED)
    except ValueError as error:
        raise PdlcError(str(error)) from None
    if not find_marked_comments(issue, "DECISION"):
        raise PdlcError("no PDLC-DECISION comment on this record — nothing to resolve")

    entries = load_json_array("--manifest", manifest_path, allow_empty=False)
    _validate(entries)
    attachments = save_attachments(work_item_number(record), attachment_inputs)

    deferred: dict[int, dict] = {}
    for index, entry in enumerate(entries, start=1):
        if "defer" in entry:
            deferred[index] = _defer(issue, stage, entry["defer"])

    post_comment(issue, _resolution_body(stage, entries, deferred), "RESOLUTION")
    set_gate(record["id"], target.gate.value)

    return {
        "resolved": True,
        "itemId": record["id"],
        "work_item": int(issue),
        "stage": stage,
        "gateState": target.gate.value,
        "answered": [e["decision"].strip() for e in entries if "answer" in e],
        "deferred": [
            {"number": child["number"], "title": child["title"], "reused": child["reused"]}
            for child in deferred.values()
        ],
        "attachments": attachments,
    }


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    raw_args = command_args
    if wants_help(raw_args):
        print_help(__doc__)
        return 0
    try:
        args, attachment_inputs = parse_attachment_arguments(raw_args)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1
    if len(args) != 3 or args[1] != "--manifest":
        print("usage: pdlc post decision WORK_ITEM --manifest FILE", file=sys.stderr)
        return 1
    issue, _, manifest = args

    try:
        result = post_decision(issue, require_file("--manifest", manifest), attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
