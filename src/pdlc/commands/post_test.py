#!/usr/bin/env python3
"""NAME
    pdlc post test - complete the Testing stage and submit it for review

USAGE
    pdlc post test WORK_ITEM EVIDENCE_FILE|- --traceability FILE|- [--attachment PATH [--attachment-description TEXT]]

FLAGS
    --traceability FILE|-               required; the requirement-to-source traceability map
    --attachment PATH (repeatable)      attach a local file's contents to the evidence comment
    --attachment-description TEXT       description for the --attachment immediately before it

DESCRIPTION
    Publishes the coverage committed on the current branch, registers the
    branch's pull request on the record, persists the requirement-to-source
    traceability map verbatim into the evidence under a `## Traceability`
    heading, and sets `Review Required`.

    The current branch must be the top task branch of the implementation
    stack. The command syncs and pushes that stack itself, so the test commits
    reach the top task's pull request with every base still chained; no skill
    or sub-agent pushes a task branch by hand. The push runs only after the
    record has been validated for the transition, and before the evidence is
    posted: a failed push leaves the record untouched, while a failed post
    after a successful push is safe to re-run.
"""

from __future__ import annotations

import argparse
import json
import sys


from pdlc.hosts.code_host import get_code_host
from pdlc.internal.complete_transition import complete_transition, prepare_transition
from pdlc.internal.attachments import parse_attachment_arguments
from pdlc.internal.workitem import attach_pr
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import is_stdin, resolve_text, print_help, wants_help


def post_test(issue: str, evidence: str, traceability: str, attachment_inputs: list[dict]) -> dict:
    if is_stdin(evidence) and is_stdin(traceability):
        raise PdlcError("stdin can supply only one of EVIDENCE or --traceability")

    publication = prepare_transition(issue, "Testing")
    body = (
        f"{resolve_text(evidence, label='evidence').rstrip()}\n\n"
        f"## Traceability\n\n{resolve_text(traceability, label='--traceability').strip()}\n"
    )
    code_host = get_code_host()
    # The stack mechanism owns bases and rebases, so the coverage commits are
    # published through it rather than a bare `git push` of the top branch.
    code_host.submit_task_stack()
    pull_request = code_host.ensure_pull_request_linked(issue)
    attach_pr(issue, pull_request["number"])
    result = complete_transition(publication, body, attachment_inputs)
    result["pullRequest"] = pull_request
    return result


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
