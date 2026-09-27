#!/usr/bin/env python3
"""NAME
    pdlc prompt plan-reviewer - write the reviewer's brief for a pass's delivery-task plans; nothing is published to the backend

USAGE
    - when reviewing a planning pass:
      pdlc prompt plan-reviewer WORK_ITEM --manifest FILE [--findings FILE|text:BODY]
    - when reviewing the recorded plans as they stand, such as plans published without review:
      pdlc prompt plan-reviewer WORK_ITEM [--findings FILE|text:BODY]

DESCRIPTION
    Writes the complete brief for the reviewer checking a pass's delivery-task
    plans before they are posted to the work item store. It prints only the
    brief file's path; that file is sent to that sub-agent verbatim.

    `--manifest` is the plan manifest `pdlc prompt tech-planner` generated, the
    same one `pdlc post plan` takes. The brief names each task file for the
    reviewer to read rather than inlining it, marking whether its plan is new,
    unchanged from the recorded plan, or replaces it; a replaced plan's
    recorded text is inlined, since the file no longer shows it. The parent's
    complete body is always inlined too. A task file that no longer has its
    task and tech plan blocks is refused with a pointer to the dry run.

    Without `--manifest`, the command writes the record's open, unimplemented
    tasks and their recorded plans to fresh task files and a manifest in the
    work-item cache, exactly as `pdlc prompt tech-planner` does, and briefs the
    reviewer on those; the brief names the manifest, which `pdlc post plan`
    then takes. It refuses unless the record's `Status` is `Technical Plan`
    and a delivery task is open and unimplemented.

    The command records the exact manifest and task files it hands the
    reviewer in the work-item cache, and `pdlc post plan` lands only those
    files unchanged. If a file recorded by an earlier review changed since,
    the command first restores each to the reviewed version, keeps the edited
    copy beside it as `<name>.rejected.md`, and refuses so that review is
    discarded and redone.

    `--findings` carries the previous pass's findings on a re-review, so each
    can be confirmed addressed; with nothing given, the brief has no prior
    findings section.

    The command also writes a fresh findings file, an outline of the report,
    to a fixed path in the work-item cache and names it in the brief; the
    reviewer writes its findings there. Each brief overwrites the previous
    one's file, after reading `--findings`, so that file may be passed back as
    `--findings` on the re-review. A successful landing of the reviewed
    files deletes it.

FLAGS
    --manifest FILE             the plan manifest to review; omit it to review the recorded plans
    --findings FILE|text:BODY   the previous pass's findings, on a re-review

EXAMPLES
    pdlc prompt plan-reviewer 236 --manifest /tmp/pdlc-plan.json
    pdlc prompt plan-reviewer 236 --manifest /tmp/pdlc-plan.json --findings text:"resolve the spike"
    pdlc prompt plan-reviewer 236
"""

from __future__ import annotations

import argparse
import sys

from pdlc.commands import prompt
from pdlc.internal.inputs import print_help, wants_help

COMMAND = "plan-reviewer"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    if wants_help(command_args):
        print_help(__doc__)
        return 0

    parser = argparse.ArgumentParser(description="Print the reviewer's brief for a pass's delivery-task plans")
    prompt.add_common_arguments(parser, COMMAND)
    parser.add_argument("--manifest", help="the plan manifest file; omit it to review the recorded plans")
    parser.add_argument("--findings", help="the previous pass's findings (FILE or text:BODY)")
    args = parser.parse_args(command_args)

    return prompt.run(COMMAND, args, lambda: prompt.plan_reviewer_brief(args.work_item, args.manifest, args.findings))


if __name__ == "__main__":
    raise SystemExit(main())
