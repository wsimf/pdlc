#!/usr/bin/env python3
"""Read-only: renders a work item's metadata, task tree, linked pull requests,
and routing decision for the pdlc skill's Orient mode.

Sections are ordered front matter, `# Work Item`, `## Attachments`,
`## User Comments`, `# Tasks`, `# Due Next`.

`## Attachments` lists local Work Item attachments with their descriptions and
resolved paths. `## User Comments` carries every comment on the record that has
no `PDLC-*` marker — human or outside-bot discussion — oldest first; one comment
fetch feeds both the full and compact renders.

By default the complete inspection is written to a file under the system temp
directory and stdout carries a compact index. Use `--full` for the complete
inspection on stdout, or `--file` to print the complete inspection's path.

    pdlc inspect ISSUE_NUMBER
    pdlc inspect ISSUE_NUMBER --full
    pdlc inspect ISSUE_NUMBER --file

Always includes a `# Tasks` section: every delivery task as its own YAML
front-matter block (number, title, completed, isUI, hasPlan,
hasImplementation, needsPlan) — metadata only, no body. `hasPlan` is true once
a task has been technically planned; `hasImplementation` is true once
implementation work has been carried out for it. A single GraphQL call computes
every flag, so this costs nothing extra; it omits the body text itself, which is
usually only needed for a handful of tasks. Fetch those with
`pdlc inspect task DELIVERY_TASK [DELIVERY_TASK ...]`. Dependency closure and
HITL approval still require reading a candidate's body and the record's own
comments; this stops short of that judgment. Evidence comments are
deliberately not included — they are read through their own script.

Also includes a `# Due Next` section: the same `(Status, Gate State) → action`
table pdlc next routes on, applied read-only — it looks ahead through
any consecutive stages declared in `Skipped States` the same way that script's
skip cascade does, but never posts a comment or writes work item state. This is
what tells a caller what's actually due without hand-applying the table in
pdlc/SKILL.md itself.

The default compact output retains the metadata, task tree, and routing needed
for orientation, and points at the full file with the raw work item body.

    ---
    id: PVTI_...                        work item ID, not the work item ID
    content:
      number: 18
      title: "..."
      url: "..."
    Status: Product                     work item fields; any of
    Gate State: Approval Required       the three may be null
    Lifecycle: Planning
    Skipped States: ""                  comma-joined stage names, or empty
    pullRequests:                       registered on the record + its tasks
      - number: 139
        title: "..."
        url: "..."
        state: OPEN | CLOSED | MERGED
        isDraft: false
        branch: "feat/..."             head ref
        mergedAt: "..." | null
        checks: SUCCESS | FAILURE | PENDING | ... | NONE
    ---

    # Work Item

    Full body in /tmp/pdlc-work-18.md
    Read lines 14-48 in /tmp/pdlc-work-18.md for the body.

    ## Attachments

    ## User Comments

    # Tasks

    ---
    number: 45
    title: "WORK-42-TASK-001 [CORE] Add foo"
    completed: false
    isUI: false
    hasPlan: true
    hasImplementation: false
    needsPlan: false
    ---

    # Due Next

    Due next: Implementation.Pending → pdlc-implement
    Next eligible delivery task is due.

or, with one or more stages bypassed via `Skipped States`:

    # Due Next

    Skipped through: UI, Tasks (declared in Skipped States)
    Due next: Technical Plan.Pending → pdlc-plan
    Technical plan is due.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


from pdlc.internal.pull_requests import record_pull_requests  # type: ignore
from pdlc.internal.attachments import attachments_for_item, attachments_markdown  # type: ignore
from pdlc.domain.lifecycle import PdlcError  # type: ignore
from pdlc.internal.reporting import yaml_front_matter  # type: ignore
from pdlc.internal.workitem import due_next, item_gate, item_skipped_states, ref_label, resolve_item, strip_task_meta, task_tree, user_comments_markdown  # type: ignore

# Translates due_next()'s bare action into the script name (or human role) a
# caller would actually name in a report — the same distinction pdlc/SKILL.md's
# "Next action by state" table draws between an ordinary Approval Required
# (pdlc post approve) and Verification's (pdlc post complete), which due_next()
# itself doesn't need to know since it only routes, never names a script.
_OWNER_FOR_ACTION = {
    "pdlc-write": "pdlc-write",
    "pdlc-review": "pdlc-review",
    "pdlc-tasks": "pdlc-tasks",
    "pdlc-plan": "pdlc-plan",
    "pdlc-implement": "pdlc-implement",
    "pdlc-test": "pdlc-test",
    "pdlc-verify": "pdlc-verify",
}


def _due_next_owner(due: dict) -> str:
    action = due["action"]
    if action == "human-approval":
        return "human — pdlc post complete" if due["status"] == "Verification" else "human — pdlc post approve"
    if action == "human-decision":
        return "human — resolve the blocking review decision (see the PDLC-DECISION comment)"
    if action == "pdlc-post-ci":
        return "pdlc post ci — record the shared PR's CI outcome"
    if action == "none":
        return "none — record is Complete"
    if action == "blocked":
        return "blocked — malformed work item state"
    return _OWNER_FOR_ACTION.get(action, action)


def _due_next_section(item: dict) -> str:
    due = due_next(item)
    lines = []
    if due["skipped_through"]:
        lines.append(f"Skipped through: {', '.join(due['skipped_through'])} (declared in Skipped States)")
    lines.append(f"Due next: {due['state']} → {_due_next_owner(due)}")
    lines.append(due["reason"].capitalize() + ".")
    if due["gate"] == "Approval Required" and due["status"] in ("Product", "UI", "Tasks", "Technical Plan"):
        lines.append(
            "A driver request to change this artifact re-enters its owning skill "
            "(pdlc-write / pdlc-tasks / pdlc-plan): the land script returns the "
            "stage to Stale itself and re-lands the reviewed artifact in one step."
        )
    if item_gate(item) == "CI Pending":
        lines.append(
            "Orientation is read-only: report the pullRequests checks state above and, on continue, "
            "follow references/resolve-ci.md."
        )
    return "# Due Next\n\n" + "\n".join(lines)


def _task_front_matter(task: dict) -> str:
    return yaml_front_matter({
        "number": task["number"],
        "title": task["title"],
        "completed": task["state"] == "CLOSED",
        "isUI": task["isUI"],
        "hasPlan": task["hasPlan"],
        "hasImplementation": task["hasImplementation"],
        "needsPlan": task["needsPlan"],
    })


def _compact_pull_request(pr: dict) -> dict:
    return {
        key: pr[key]
        for key in ("number", "url", "state", "checks")
        if key in pr
    }


def _compact_metadata(item: dict, pull_requests: list[dict]) -> str:
    return yaml_front_matter({
        "id": item["id"],
        "content": item["content"],
        "Status": item.get("Status"),
        "Gate State": item.get("Gate State"),
        "Lifecycle": item.get("Lifecycle"),
        "Skipped States": item_skipped_states(item),
        "pullRequests": [_compact_pull_request(pr) for pr in pull_requests],
    })


def _body_location(full_output: str, body: str, path: Path) -> str:
    if not body:
        return f"Full inspection in {path}; the work item body is empty."

    lines = full_output.splitlines()
    # `# Work Item` heading, blank line, then the body; the section that follows
    # (Attachments) is not relied on for the span.
    start = lines.index("# Work Item") + 3
    end = start + len(body.splitlines()) - 1
    return f"Full inspection in {path}; read lines {start}-{end} for the body."


def _compact_render(
    item: dict,
    pull_requests: list[dict],
    tasks: list[dict],
    attachments: list[dict],
    user_comments_section: str,
    full_output: str,
    path: Path,
) -> str:
    body = strip_task_meta(item.get("issueBody") or "").rstrip("\n")
    sections = [_compact_metadata(item, pull_requests)]
    sections.append(f"# Work Item\n\n{_body_location(full_output, body, path)}")
    sections.append(attachments_markdown(attachments))
    sections.append(user_comments_section)

    if not tasks:
        sections.append("# Tasks\n\nNo Tasks")
    else:
        task_blocks = "\n\n".join(_task_front_matter(task) for task in tasks)
        sections.append(f"# Tasks\n\n{task_blocks}")

    sections.append(_due_next_section(item))
    return "\n\n".join(sections) + "\n"


def render(issue: str) -> tuple[str, str, Path]:
    item = resolve_item(issue)
    pull_requests = record_pull_requests(issue)
    attachments = attachments_for_item(item)

    metadata = {
        "id": item["id"],
        "content": item["content"],
        "Status": item.get("Status"),
        "Gate State": item.get("Gate State"),
        "Lifecycle": item.get("Lifecycle"),
        "Skipped States": item_skipped_states(item),
        "pullRequests": pull_requests,
    }

    # One comment fetch feeds the `## User Comments` section in both renders.
    user_comments_section = user_comments_markdown(issue)

    # Strip the machine-owned `<!-- pdlc:meta -->` block: its registered PR
    # numbers are already surfaced in the front matter above, and the raw
    # comment is noise in the rendered body (inspect_task strips it too).
    body = strip_task_meta(item.get("issueBody") or "").rstrip("\n")

    sections = [yaml_front_matter(metadata)]
    sections.append(f"# Work Item\n\n{body}")
    sections.append(attachments_markdown(attachments))
    sections.append(user_comments_section)

    tasks = task_tree(issue)
    if not tasks:
        sections.append("# Tasks\n\nNo Tasks")
    else:
        task_blocks = "\n\n".join(_task_front_matter(task) for task in tasks)
        sections.append(f"# Tasks\n\n{task_blocks}")

    sections.append(_due_next_section(item))

    full_output = "\n\n".join(sections) + "\n"
    path = Path(tempfile.gettempdir()) / f"{ref_label()}-{issue}.md"
    compact_output = _compact_render(
        item, pull_requests, tasks, attachments, user_comments_section, full_output, path
    )
    return full_output, compact_output, path


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a PDLC work item")
    parser.add_argument("work_item")
    parser.add_argument(
        "--full", action="store_true",
        help="print the complete inspection to stdout",
    )
    parser.add_argument(
        "--file", action="store_true",
        help="write to {TEMPDIR}/{repo}-{issue}.md and print that path instead of stdout",
    )
    args = parser.parse_args()

    if args.full and args.file:
        parser.error("--full and --file cannot be used together")

    try:
        full_output, compact_output, path = render(args.work_item)
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    if args.file:
        path.write_text(full_output)
        print(path)
    elif args.full:
        sys.stdout.write(full_output)
    else:
        path.write_text(full_output)
        sys.stdout.write(compact_output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
