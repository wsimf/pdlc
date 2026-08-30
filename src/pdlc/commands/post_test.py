#!/usr/bin/env python3
"""Complete the Testing stage and submit it for review.

Confirms the shared implementation PR still links the parent (the coverage is
committed on the same branch, so it rides that PR), persists the
requirement-to-source traceability map verbatim into the evidence under a
`## Traceability` heading so the independent reviewer audits the exact
artifact the stage produced, and sets `Review Required` — all in one step.

    pdlc-post-test.py WORK_ITEM EVIDENCE_FILE|- --traceability FILE|- [--attachment PATH [--attachment-description TEXT]]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


from pdlc.hosts.code_host import get_code_host  # type: ignore
from pdlc.internal.complete_transition import complete_transition  # type: ignore
from pdlc.internal.attachments import parse_attachment_arguments  # type: ignore
from pdlc.domain.lifecycle import PdlcError, evidence_source, print_help, wants_help  # type: ignore


def _read(label: str, source: str) -> str:
    path, is_temporary = evidence_source(label, source)
    try:
        return path.read_text()
    finally:
        if is_temporary:
            path.unlink(missing_ok=True)


def post_test(issue: str, evidence: str, traceability: str, attachment_inputs: list[dict]) -> dict:
    if evidence == "-" and traceability == "-":
        raise PdlcError("stdin can supply only one of EVIDENCE or --traceability")

    pull_request = get_code_host().ensure_pull_request_linked(issue)

    body = (
        f"{_read('evidence', evidence).rstrip()}\n\n"
        f"## Traceability\n\n{_read('--traceability', traceability).strip()}\n"
    )
    result = complete_transition(issue, body, "Testing", attachment_inputs)
    result["pullRequest"] = pull_request
    return result


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

    parser = argparse.ArgumentParser(description="Complete the PDLC Testing stage")
    parser.add_argument("work_item")
    parser.add_argument("evidence", help="Evidence body — a file path, or - for stdin")
    parser.add_argument("--traceability", required=True, help="Traceability map — a file path, or - for stdin")
    args = parser.parse_args(script_args)

    try:
        result = post_test(args.work_item, args.evidence, args.traceability, attachment_inputs)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
