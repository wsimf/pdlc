"""Pure policy for correcting a landed upstream artifact in place.

A patch lands an upstream stage's artifact while the record stays on its
active stage. The commands that land each artifact call these helpers for the
decisions that need no host I/O: whether an impact report is required, what
its verdict permits, and the script-owned opening of the `PDLC-PATCHED`
comment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import evidence_comment_text, find_marked_comments, latest_marked_comment
from pdlc.domain.workflow import Event, Pipeline, State

NO_IMPACT = "none"
_VERDICT = re.compile(r"^Earliest affected stage:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
_PATCHED_STAGE = re.compile(r"^Patched stage:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class PatchPlan:
    """A validated patch: the stage whose artifact lands, the active state it
    lands from and to, and the stages between them an impact report covers."""

    patched_stage: str
    source: State
    target: State
    intermediate: tuple[str, ...]

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


def require_no_impact(plan: PatchPlan, report: str | None) -> None:
    """Refuse a patch whose required impact report is missing or names an
    affected stage; an optional report, when given, must still permit it."""
    if report is None:
        if plan.impact_required:
            raise PdlcError(
                f"--impact is required: {', '.join(plan.intermediate)} lie between "
                f"{plan.patched_stage} and {plan.source.stage}"
            )
        return
    verdict = impact_verdict(report)
    if verdict != NO_IMPACT:
        raise PdlcError(
            f"the impact report names {verdict} as affected; return it to Stale with "
            f"`pdlc post invalidate` instead of patching {plan.patched_stage}"
        )


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


def patch_comment(plan: PatchPlan, report: str | None) -> str:
    """The `PDLC-PATCHED` body: script-owned lines, then the impact report."""
    impact = (report or "").strip() or "No intermediate stages."
    return (
        f"Patched stage: {plan.patched_stage}\n"
        f"Active stage: {plan.source.stage} / {plan.source.gate.value}\n\n"
        f"{impact}\n"
    )


def patches_since_approval(comments: list[dict]) -> list[dict]:
    """Every `PDLC-PATCHED` comment newer than the record's last approval,
    oldest first, each tagged with its `patchedStage`: the upstream changes
    the driver has not yet approved past."""
    approval = latest_marked_comment(comments, ("APPROVED", "AUTOAPPROVED"))
    since = approval["createdAt"] if approval else ""
    patches = []
    for comment in find_marked_comments(comments, "PATCHED"):
        if comment["createdAt"] <= since:
            continue
        match = _PATCHED_STAGE.search(evidence_comment_text(comment))
        patches.append({**comment, "patchedStage": match.group(1) if match else "unknown"})
    return patches
