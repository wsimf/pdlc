#!/usr/bin/env python3
"""Routes one work item's (Status, Gate State) to the next pdlc-* skill to run,
using the work item's configured workflow policy.

    pdlc next [--work-item N]        one item, or scan the queue for the
                                            next autonomous action
    pdlc next loop [--work-item N]   same, but retry with backoff while
                                            nothing is actionable before giving up

Output is a Markdown document: YAML front matter — id, work_item_number, title,
current_status, next_status, action — followed by a one-line instruction. The
dispatched skill resolves the record itself with pdlc-inspect; the routing
decision is all this script hands over.

`action` is a pdlc-* skill name, `pdlc-post-ci` (run the script, then re-poll),
or `human-approval` / `human-decision` / `blocked` / `none`.

One routing side effect mutates the record before the decision is returned, the
same way for a single --work-item lookup or a queue scan:

  - skip cascade: a stage listed in "Skipped States" is bypassed with a
    PDLC-SKIPPED comment and the state advanced past it.

Churn-gated auto-approval of the Implementation/Testing approval gates is not
done here — the script that writes each gate (lib/ci_gate.py, pdlc post review)
advances straight past it, so this router only ever sees real on-disk state.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path


from pdlc.internal.ci_gate import peek_ci_state  # type: ignore
from pdlc.domain.lifecycle import PdlcError, print_help  # type: ignore
from pdlc.domain.model import blocked_reason, next_state_hint  # type: ignore
from pdlc.domain.workflow import Event, Gate, Lifecycle, PIPELINE_REGISTRY, Pipeline, State  # type: ignore
from pdlc.internal.reporting import yaml_front_matter  # type: ignore
from pdlc.internal.workitem import (  # type: ignore
    is_stage_skipped,
    item_gate,
    item_issue,
    item_status,
    post_comment,
    project_items,
    resolve_item,
    set_state,
)


# The routing decision handed to the orchestrator: which record, where it sits,
# and what runs next. No body or comments — the dispatched skill inspects the
# record itself.
def decision(item: dict, action: str, reason: str, current_status: str, next_status: str) -> dict:
    content = item.get("content") or {}
    return {
        "id": item.get("id"),
        "work_item_number": content.get("number", item.get("number")),
        "title": content.get("title", item.get("title")),
        "current_status": current_status,
        "next_status": next_status,
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
            pipeline.validate_state(state)
        except ValueError:
            break
        if state.gate not in (Gate.PENDING, Gate.CHANGES_REQUIRED, Gate.STALE):
            break
        if not is_stage_skipped(item, state.stage):
            break

        item_id = item["id"]
        issue = item_issue(item)

        descriptor, name = tempfile.mkstemp()
        with os.fdopen(descriptor, "w") as handle:
            handle.write(f"{state.stage} skipped (declared in Skipped States).\n")
        try:
            post_comment(issue, name, "SKIPPED")
        finally:
            Path(name).unlink(missing_ok=True)

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
    for summary in project_items().get("items", []):
        candidate = resolve_item(item_issue(summary))
        try:
            pipeline = PIPELINE_REGISTRY.for_record(candidate)
            status = item_status(candidate)
            lifecycle = candidate.get("Lifecycle") or (Lifecycle.COMPLETED if status == pipeline.terminal_stage else Lifecycle.PLANNING)
            state = State.parse(status, item_gate(candidate), lifecycle)
            route = pipeline.route(state)
        except (TypeError, ValueError):
            route = None
        if route is None:
            if fallback is None:
                fallback = candidate
            continue
        # A CI-Pending record is only actionable once its checks have settled;
        # while they run it is a back-off, not a dispatch.
        if state.gate == Gate.CI_PENDING and peek_ci_state(item_issue(candidate)) == "pending":
            if fallback is None:
                fallback = candidate
            continue
        if route.autonomous:
            return candidate
        if fallback is None and route.action.value != "none":
            fallback = candidate
    return fallback


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
        return decision(item, "blocked", blocked_reason(str(error)), notation, notation)

    item = _advance_past_skips(item, pipeline)

    # CI Pending is resolved by pdlc post ci, but only once the checks have
    # finished — while they run there is genuinely nothing to do, so report it
    # as no work and let loop_ back off.
    if item_gate(item) == Gate.CI_PENDING.value and peek_ci_state(item_issue(item)) == "pending":
        return {"action": "none", "reason": f"CI is still running for work item {item_issue(item)}"}

    status = item_status(item)
    lifecycle = item.get("Lifecycle") or (Lifecycle.COMPLETED if status == pipeline.terminal_stage else Lifecycle.PLANNING)
    try:
        state = State.parse(status, item_gate(item), lifecycle)
        route = pipeline.route(state)
    except (TypeError, ValueError):
        route = None
    if route is None:
        notation = f"{status.replace(' ', '')}.{item_gate(item).replace(' ', '')}"
        return decision(item, "blocked", "missing or unsupported work item state", notation, notation)
    next_hint = state if route.action.value == "blocked" else next_state_hint(pipeline, state)
    return decision(item, route.action.value, route.reason, state.notation, next_hint.notation)


# Retries next_once with exponential backoff, but only while nothing is
# actionable ("none"): API errors and malformed state raise immediately since
# retrying those would hide a real failure. Each wait and the final give-up are
# printed to stderr so the caller can see why the loop returned.
def loop_(selector: str | None) -> tuple[dict, int | None]:
    max_attempts = int(os.environ.get("PDLC_MAX_ATTEMPTS", "5"))
    delay = int(os.environ.get("PDLC_INITIAL_DELAY_SECONDS", "60"))
    max_delay = int(os.environ.get("PDLC_MAX_DELAY_SECONDS", "900"))
    no_sleep = bool(os.environ.get("PDLC_NO_SLEEP"))

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


# Renders the routing decision as front matter + a one-line instruction.
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
        "next_status": result["next_status"],
        "action": action,
    })

    if action == "human-approval":
        instruction = (
            f"Work item {number} is at {result['current_status']} and needs explicit human approval. "
            f"Stop and tell the driver which record and stage awaits them."
        )
    elif action == "human-decision":
        instruction = (
            f"Work item {number} is at {result['current_status']} (Gate State = Decision Required): a reviewer "
            f"raised a blocking finding that only the driver can resolve. Stop, and point the driver at the "
            f"PDLC-DECISION comment on the record."
        )
    elif action == "pdlc-post-ci":
        instruction = (
            f"Work item {number} is at {result['current_status']}: the implementation review passed and "
            f"the shared PR's CI has finished. Run "
            f"`pdlc post ci {number}` to record the outcome — it "
            f"advances to Approval Required on green, or back to Changes Required on red — then re-poll."
        )
    elif action == "blocked":
        reason = result.get("reason") or "workflow routing is blocked"
        instruction = f"Work item {number} is blocked at {result['current_status']}. {_sentence(reason)}."
        if not reason.startswith("stop here"):
            instruction += " Stop and report it exactly."
    else:
        instruction = f"{_sentence(result['reason'])}. Invoke `{action}` for work item {number}."

    return f"{front}\n\n# Next Action\n\n{instruction}\n"


def main() -> int:
    args = sys.argv[1:]
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
