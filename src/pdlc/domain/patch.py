"""Pure policy for correcting a landed upstream artifact in place.

A patch lands an upstream stage's artifact while the record stays on its
active stage, or, when the independent impact report names an affected stage
in between, returns the record to that stage at Stale. The commands that land
each artifact call these helpers for the decisions that need no host I/O:
whether an impact report is required, where its verdict moves the record,
which requirements a Product patch changes, and the script-owned opening of
the `PDLC-PATCHED` comment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import evidence_comment_text, find_marked_comments, latest_marked_comment
from pdlc.domain.workflow import Event, Pipeline, State

NO_IMPACT = "none"
_VERDICT = re.compile(r"^Earliest affected stage:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_PATCHED_STAGE = re.compile(r"^Patched stage:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_CHANGED_REQUIREMENTS = re.compile(r"^Changed requirements:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
# A requirement statement opens a line, optionally as a list item and bolded:
# `- FR-4: ...`, `1. **C-2**: ...`. It runs until a blank line, a heading, or
# the next list item.
_STATEMENT_START = re.compile(r"^[ \t]*(?:[-*+][ \t]+|[0-9]+[.)][ \t]+)?\**((?:FR|C)-[0-9]+)\**[ \t]*:")
_STATEMENT_END = re.compile(r"^[ \t]*(?:$|#|[-*+][ \t]|[0-9]+[.)][ \t])")


@dataclass(frozen=True)
class PatchPlan:
    """A validated patch: the stage whose artifact lands, the active state it
    lands from and to, and the stages between them an impact report covers.
    `rewind` names the intermediate stage the impact report found affected;
    `target` is then that stage at Stale."""

    patched_stage: str
    source: State
    target: State
    intermediate: tuple[str, ...]
    rewind: str | None = None

    @property
    def impact_required(self) -> bool:
        return bool(self.intermediate)


def plan_patch(pipeline: Pipeline, source: State, patched_stage: str, skipped: set[str] | frozenset[str]) -> PatchPlan:
    """Validate that the active state may patch `patched_stage`, or raise
    `PdlcError` naming why not. A refusal points at the normal path when the
    patched stage is the active one."""
    if source.stage == pipeline.terminal_stage:
        raise PdlcError("record is Complete and locked; it cannot be patched")
    if patched_stage == source.stage:
        raise PdlcError(f"the record is at {source.stage}; land it normally instead of with --patch")
    if patched_stage in skipped:
        raise PdlcError(f"{patched_stage} is declared in Skipped States; there is no landed artifact to patch")
    try:
        target = pipeline.next_state(source, Event.PATCHED, requested_target=patched_stage)
    except ValueError as error:
        raise PdlcError(str(error)) from None
    return PatchPlan(patched_stage, source, target, pipeline.intermediate_stages(patched_stage, source.stage, skipped))


def impact_verdict(report: str) -> str:
    """The earliest affected stage an impact report names, or `none`."""
    match = _VERDICT.search(report)
    if match is None:
        raise PdlcError("--impact names no verdict; it must contain a line `Earliest affected stage: <stage|none>`")
    return match.group(1)


def apply_impact(pipeline: Pipeline, plan: PatchPlan, report: str | None) -> PatchPlan:
    """Resolve where the patch leaves the record from its impact report.

    A missing report is refused when one is required. A `none` verdict keeps
    the plan; a verdict naming one of the intermediate stages rewinds the
    record to that stage at Stale; any other verdict is refused."""
    if report is None:
        if plan.impact_required:
            raise PdlcError(
                f"--impact is required: {', '.join(plan.intermediate)} lie between "
                f"{plan.patched_stage} and {plan.source.stage}"
            )
        return plan
    verdict = impact_verdict(report)
    if verdict == NO_IMPACT:
        return plan
    if verdict not in plan.intermediate:
        allowed = ", ".join((*plan.intermediate, NO_IMPACT))
        raise PdlcError(f"the impact report names {verdict}, but its verdict must be one of: {allowed}")
    try:
        target = pipeline.next_state(plan.source, Event.INVALIDATED, requested_target=verdict)
    except ValueError as error:
        raise PdlcError(str(error)) from None
    return replace(plan, target=target, rewind=verdict)


def require_same_ids(label: str, landed: list[str], draft: list[str], invalidate: str) -> None:
    """Refuse a patch that changes a set of identifiers a later stage relies on."""
    added = sorted(set(draft) - set(landed))
    removed = sorted(set(landed) - set(draft))
    if not added and not removed:
        return
    changes = "; ".join(part for part in (
        f"adds {', '.join(added)}" if added else "",
        f"removes {', '.join(removed)}" if removed else "",
    ) if part)
    raise PdlcError(
        f"a patch must keep the landed {label} ids, but this one {changes}; "
        f"return {invalidate} to Stale with `pdlc post invalidate` instead"
    )


def requirement_statements(product: str) -> dict[str, str]:
    """Each `FR-*` / `C-*` statement a Product section declares, keyed by id,
    with its whitespace collapsed so rewrapping is not a change."""
    statements: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in product.splitlines():
        start = _STATEMENT_START.match(line)
        if start:
            current = statements.setdefault(start.group(1), [])
            current.append(line[start.end():])
        elif current is not None and not _STATEMENT_END.match(line):
            current.append(line)
        else:
            current = None
    return {key: " ".join(" ".join(parts).split()) for key, parts in statements.items()}


def requirement_changes(landed: str, draft: str) -> list[dict]:
    """The requirements a Product patch adds, removes, or rewords, in id
    order, each with its landed (`before`) and patched (`after`) statement."""
    before = requirement_statements(landed)
    after = requirement_statements(draft)

    def order(key: str) -> tuple[str, int]:
        prefix, number = key.split("-")
        return prefix, int(number)

    changes = []
    for key in sorted(before.keys() | after.keys(), key=order):
        if before.get(key) == after.get(key):
            continue
        kind = "added" if key not in before else "removed" if key not in after else "changed"
        changes.append({"id": key, "change": kind, "before": before.get(key), "after": after.get(key)})
    return changes


def _changes_section(changes: list[dict]) -> str:
    lines = ["## Requirement Changes", ""]
    for change in changes:
        lines.append(f"### {change['id']} ({change['change']})")
        if change["before"] is not None:
            lines.append(f"- Before: {change['before']}")
        if change["after"] is not None:
            lines.append(f"- After: {change['after']}")
        lines.append("")
    return "\n".join(lines)


def patch_comment(plan: PatchPlan, report: str | None, changes: list[dict] | None = None) -> str:
    """The `PDLC-PATCHED` body: script-owned lines, the requirement changes a
    Product patch makes, then the impact report."""
    header = [f"Patched stage: {plan.patched_stage}", f"Active stage: {plan.source.stage} / {plan.source.gate.value}"]
    if plan.rewind:
        header.append(f"Returned to: {plan.rewind} / {plan.target.gate.value}")
    if changes:
        header.append("Changed requirements: " + ", ".join(f"{change['id']} ({change['change']})" for change in changes))
    parts = ["\n".join(header)]
    if changes:
        parts.append(_changes_section(changes))
    parts.append((report or "").strip() or "No intermediate stages.")
    return "\n\n".join(part.strip() for part in parts) + "\n"


def patches_since_approval(comments: list[dict]) -> list[dict]:
    """Every `PDLC-PATCHED` comment newer than the record's last approval,
    oldest first, each tagged with its `patchedStage` and the
    `changedRequirements` line it records, if any: the upstream changes the
    driver has not yet approved past."""
    approval = latest_marked_comment(comments, ("APPROVED", "AUTOAPPROVED"))
    since = approval["createdAt"] if approval else ""
    patches = []
    for comment in find_marked_comments(comments, "PATCHED"):
        if comment["createdAt"] <= since:
            continue
        text = evidence_comment_text(comment)
        match = _PATCHED_STAGE.search(text)
        changed = _CHANGED_REQUIREMENTS.search(text)
        patches.append({
            **comment,
            "patchedStage": match.group(1) if match else "unknown",
            "changedRequirements": changed.group(1) if changed else None,
        })
    return patches
