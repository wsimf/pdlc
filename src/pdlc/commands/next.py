#!/usr/bin/env python3
"""NAME
    pdlc next - route one work item (or the queue) to the next pdlc-* skill

USAGE
    pdlc next [--work-item N]        one item, or scan the queue for the
                                            next autonomous action
    pdlc next loop [--work-item N]   same, but retry with backoff while
                                            nothing is actionable before giving up

DESCRIPTION
    Routes one work item's (Status, Gate State) to the next pdlc-* skill to run,
    using the work item's configured workflow policy.

Output is a Markdown document: YAML front matter — id, work_item_number, title,
current_status, action — followed by the routed record's `# Due Next` section,
exactly as `pdlc inspect WORK_ITEM` renders it for the same state. That
section is the instruction to carry out; the dispatched skill still resolves
the record itself with `pdlc inspect`.

`action` classifies that instruction for a caller deciding whether to act
without a human: a pdlc-* skill name or `pdlc-post-ci` is autonomous;
`human-input` / `human-approval` / `human-decision` / `blocked` are stops. It
always agrees with the skill or command `# Due Next` names — for example a
UI, Tasks, or Technical Plan record at Review Required routes to its owning
skill, which reviews the published artifact and re-lands it, and a Changes
Required or Stale record with no change request to act on routes to
`human-input`, because its `# Due Next` asks for the user's confirmation. The
queue scan still selects by stage and gate, so it can surface such a record
as a stop ahead of later autonomous work. An empty queue scan and a Complete
record carry `action: none` and a short notice instead of a `# Due Next`
section. A CI Pending record routes to `pdlc-post-ci`; its command waits for
the registered PR stack to settle.

Two routing side effects mutate the record before the decision is returned,
the same way for a single --work-item lookup or a queue scan:

  - skip cascade: a stage listed in "Skipped States" is bypassed with a
    PDLC-SKIPPED comment and the state advanced past it.
  - self-heal: a stage/gate combination no pdlc command ever writes, but that
    has exactly one sane reading, is corrected rather than reported as
    blocked — see `pipeline.heal()` and `pdlc continue --help` for the exact
    cases (a stray Approved gate, CI Pending on a stage that isn't
    CI-gated, or Review Required on Verification, which has no review).
    A stray Approved whose stage evidence `pdlc post approve` would refuse
    lands on that stage's own Approval Required instead.
    `pdlc continue` exposes this same correction standalone.

Churn-gated auto-approval of the Implementation/Testing approval gates is not
done here — the script that writes each gate (lib/ci_gate.py, pdlc post review)
advances straight past it, so this router only ever sees real on-disk state.
"""

from __future__ import annotations

import sys
from pdlc.config import get_config
import time


from pdlc.commands.inspect import due_next_section
from pdlc.internal.ci_gate import peek_ci_state
from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.inputs import print_help
from pdlc.domain.model import blocked_reason
from pdlc.domain.stages import Gate
from pdlc.domain.workflow import Event, Lifecycle, Pipeline, State
from pdlc.domain.workflows.pipeline import PIPELINE_REGISTRY
from pdlc.internal.reporting import yaml_front_matter
from pdlc.internal.workitem import (
    heal_item,
    is_stage_skipped,
    item_gate,
    item_issue,
    item_status,
    post_comment,
    queue_items,
    resolve_item,
    set_state,
)


# The routing decision handed to the orchestrator: which record, where it sits,
# and what runs next. No body or comments — the dispatched skill inspects the
# record itself.
def decision(item: dict, action: str, reason: str, current_status: str) -> dict:
    content = item.get("content") or {}
    return {
        "id": item.get("id"),
        "work_item_number": content.get("number", item.get("number")),
        "title": content.get("title", item.get("title")),
        "current_status": current_status,
        "action": action,
        "reason": reason,
    }


# When the arriving stage was pre-declared in the work item's "Skipped States"
# field (see pdlc post skip), bypass its specialist skill entirely instead of
# routing to it: post a PDLC-SKIPPED comment and advance state automatically.
# Cascades through consecutive skipped stages. Verification is terminal — a
# skipped Verification stops at Approval Required rather than Complete, so
# pdlc post complete still requires an explicit human completion instead of one
# being triggered silently.
def advance_past_skips(item: dict) -> dict:
    pipeline = PIPELINE_REGISTRY.for_record(item)
    return _advance_past_skips(item, pipeline)


def _advance_past_skips(item: dict, pipeline: Pipeline) -> dict:
    while True:
        status = item_status(item)
        gate = item_gate(item)
        lifecycle = item.get("Lifecycle") or (Lifecycle.COMPLETED if status == pipeline.terminal_stage else Lifecycle.PLANNING)

        try:
            state = State.parse(status, gate, lifecycle)
        except ValueError:
            break

        if heal_item(item, item_issue(item), pipeline, state) is not None:
            continue

        try:
            pipeline.validate_state(state)
        except ValueError:
            break
        if state.gate not in (Gate.PENDING, Gate.CHANGES_REQUIRED, Gate.STALE):
            break
        if not is_stage_skipped(item, state.stage):
            break

        item_id = item["id"]
        issue = item_issue(item)

        post_comment(issue, f"{state.stage} skipped (declared in Skipped States).\n", "SKIPPED")

        target = pipeline.next_state(state, Event.SKIPPED)
        set_state(item_id, target.stage, target.gate.value, target.lifecycle.value)
        item["Status"] = target.stage
        item["Gate State"] = target.gate.value
        item["Lifecycle"] = target.lifecycle.value

    return item


# The first queue item with an autonomous action, else the first one blocked on
# a human (so the caller learns it's waiting rather than getting a bare "none").
def scan_for_candidate() -> dict | None:
    fallback: dict | None = None
    for summary in queue_items():
        issue = item_issue(summary)
        if not issue:
            continue
        try:
            pipeline = PIPELINE_REGISTRY.for_record(summary)
            status = item_status(summary)
            lifecycle = summary.get("Lifecycle") or (Lifecycle.COMPLETED if status == pipeline.terminal_stage else Lifecycle.PLANNING)
            state = State.parse(status, item_gate(summary), lifecycle)
            route = pipeline.route(state)
        except (TypeError, ValueError):
            route = None
        if route is None:
            if fallback is None:
                fallback = summary
            continue
        # A CI-Pending record is only actionable once its checks have settled;
        # while they run it is a back-off, not a dispatch.
        if state.gate == Gate.CI_PENDING and peek_ci_state(issue) == "pending":
            if fallback is None:
                fallback = summary
            continue
        if route.autonomous:
            return resolve_item(issue)
        if fallback is None and route.action.value != "none":
            fallback = summary
    return resolve_item(item_issue(fallback)) if fallback is not None else None


# Resolves the one item to act on this call: an explicit work item number, or
# (scanning all items) the next one with something to do.
def next_once(selector: str | None) -> dict:
    if selector:
        item: dict | None = resolve_item(selector)
    else:
        item = scan_for_candidate()

    if item is None:
        return {"action": "none", "reason": "no PDLC work item is currently available"}

    try:
        pipeline = PIPELINE_REGISTRY.for_record(item)
    except (TypeError, ValueError) as error:
        status, gate = item_status(item), item_gate(item)
        notation = f"{status.replace(' ', '')}.{gate.replace(' ', '')}"
        return _with_due_next(decision(item, "blocked", blocked_reason(str(error)), notation), item)

    item = _advance_past_skips(item, pipeline)

    status = item_status(item)
    lifecycle = item.get("Lifecycle") or (Lifecycle.COMPLETED if status == pipeline.terminal_stage else Lifecycle.PLANNING)
    try:
        state = State.parse(status, item_gate(item), lifecycle)
        route = pipeline.route(state)
    except (TypeError, ValueError):
        route = None
    if route is None:
        notation = f"{status.replace(' ', '')}.{item_gate(item).replace(' ', '')}"
        return _with_due_next(decision(item, "blocked", "missing or unsupported work item state", notation), item)
    return _with_due_next(decision(item, route.action.value, route.reason, state.notation), item)


# Attaches the record's `# Due Next` section, rendered after the skip cascade
# and self-heal so it reflects the state just routed. It is the same section
# `pdlc inspect` prints, so the loop acts on one instruction for a record
# whichever command surfaced it. An evidence gate with no evidence renders a
# stop-and-confirm fallback, so its action becomes human-input to match.
def _with_due_next(result: dict, item: dict) -> dict:
    result["due_next"], unevidenced = due_next_section(item)
    if unevidenced and result["action"].startswith("pdlc-"):
        result["action"] = "human-input"
        result["reason"] = "no evidence identifies the required changes; the user must confirm how to continue"
    return result


# Retries next_once with exponential backoff, but only while nothing is
# actionable ("none"): API errors and malformed state raise immediately since
# retrying those would hide a real failure. Each wait and the final give-up are
# printed to stderr so the caller can see why the loop returned.
def loop_(selector: str | None) -> tuple[dict, int | None]:
    config = get_config()
    max_attempts = config.max_attempts
    delay = config.initial_delay_seconds
    max_delay = config.max_delay_seconds
    no_sleep = config.no_sleep

    result: dict = {"action": "none", "reason": "no PDLC work item is currently available"}
    for attempt in range(1, max_attempts + 1):
        result = next_once(selector)
        if result.get("action") != "none":
            return result, None
        if attempt == max_attempts:
            break
        print(f"No work ready, retrying in {delay}s (attempt {attempt} of {max_attempts})…", file=sys.stderr)
        if not no_sleep:
            time.sleep(delay)
        delay = min(delay * 2, max_delay)

    print(f"No work ready after {max_attempts} attempts; giving up this pass.", file=sys.stderr)
    return result, max_attempts


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


# Renders the routing decision as front matter + the record's `# Due Next`
# section (see `_with_due_next`), or a fixed notice when there is no record to act on.
def render(result: dict, *, attempts: int | None = None) -> str:
    action = result["action"]
    number = result.get("work_item_number")

    if action == "none" and result.get("reason") == "complete":
        front = yaml_front_matter({"work_item_number": number, "action": "none"})
        return f"{front}\n\n# Complete\n\nWork item {number} is complete. Nothing to do.\n"

    if action == "none":
        fields: dict = {"action": "none"}
        if attempts is not None:
            fields["attempts"] = attempts
        front = yaml_front_matter(fields)
        scanned = f"Scanned the PDLC queue {attempts} time{'s' if attempts != 1 else ''}; " if attempts is not None else ""
        reason = result.get("reason") or ""
        detail = f"{_sentence(reason)}.\n\n" if reason and "no PDLC work item" not in reason else ""
        return (
            f"{front}\n\n# No Work Ready\n\n"
            f"{detail}"
            f"{scanned}nothing is currently actionable.\n\n"
            f"Invoke this script again in ~5 min to check for new work.\n"
        )

    front = yaml_front_matter({
        "id": result.get("id"),
        "work_item_number": number,
        "title": result.get("title"),
        "current_status": result["current_status"],
        "action": action,
    })
    return f"{front}\n\n{result['due_next'].rstrip()}\n"


def main(argv: list[str] | None = None) -> int:
    command_args = list(sys.argv[1:] if argv is None else argv)
    args = command_args
    if any(arg in ("-h", "--help") for arg in args):
        print_help(__doc__)
        return 0
    loop = bool(args) and args[0] == "loop"
    if loop:
        args = args[1:]
    if args and args[0] == "--work-item":
        args = args[1:]
    selector = args[0] if args else None

    try:
        if loop:
            result, attempts = loop_(selector)
        else:
            result, attempts = next_once(selector), None
    except PdlcError as error:
        print(f"pdlc: {error}", file=sys.stderr)
        return 1

    sys.stdout.write(render(result, attempts=attempts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
