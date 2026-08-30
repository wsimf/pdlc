#!/usr/bin/env python3
"""Declares one or more lifecycle stages as skipped ahead of time, recorded in
the work item's "Skipped States" text field as a comma-separated list. Always
posts a durable PDLC-SKIPPED evidence comment naming the actor and the
skipped stage(s); --justification appends the reason. Does not itself change
Status/Gate State/Lifecycle — pdlc next consults this field when a
skipped stage is reached. Only the orchestrator may call this, and only on an
explicit human instruction, same as pdlc post approve/pdlc post complete: a skip
carries the same weight as an approval and must not be requestable by an
unattended agent — this is a procedural boundary, not an authentication
check, since gh identity cannot tell a human from an agent acting on their
behalf.

    pdlc post skip --work-item WORK_ITEM --state STATE[,STATE...] [--justification TEXT] [--attachment PATH [--attachment-description TEXT]]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


from pdlc.internal.attachments import parse_attachment_arguments, save_attachments, work_item_number  # type: ignore
from pdlc.domain.lifecycle import PdlcError, SKIPPABLE_STAGES, print_help, wants_help  # type: ignore
from pdlc.internal.workitem import (  # type: ignore
    current_actor,
    item_skipped_states,
    post_comment,
    resolve_item,
    set_skipped_states,
)


def skip(issue: str, states_arg: str, justification: str | None, attachment_inputs: list[dict]) -> dict:
    requested_states = [state.strip() for state in states_arg.split(",")]
    for state in requested_states:
        if state not in SKIPPABLE_STAGES:
            raise PdlcError(f"invalid state: {state} (expected one of: {' '.join(SKIPPABLE_STAGES)})")

    login = current_actor()

    record = resolve_item(issue)
    item_id = record["id"]

    existing_states = [state for state in item_skipped_states(record).split(",") if state]
    merged = sorted(set(existing_states) | set(requested_states))
    evidence = (
        "Stage(s) skipped.\n\n"
        f"Actor: {login}\n"
        f"Skipped: {','.join(requested_states)}\n\n"
        f"Justification: {justification or 'none provided'}\n"
    )
    attachments = save_attachments(work_item_number(record), attachment_inputs)
    set_skipped_states(item_id, ",".join(merged))
    post_comment(issue, evidence, "SKIPPED")

    return {
        "work_item": int(issue),
        "itemId": item_id,
        "skippedStates": merged,
        "actor": login,
        "commented": bool(justification),
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

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--work-item")
    parser.add_argument("--state")
    parser.add_argument("--justification")
    args = parser.parse_args(script_args)

    if not args.work_item or not args.state:
        print(
            "usage: pdlc post skip --work-item WORK_ITEM --state STATE[,STATE...] [--justification TEXT]",
            file=sys.stderr,
        )
        return 1

    try:
        result = skip(args.work_item, args.state, args.justification, attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
