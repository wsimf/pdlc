"""Pure PDLC logic with no backend I/O: parent-body section editing, delivery
task classification, evidence-comment/timeline parsing, work-item field
accessors, and the read-only routing view.

Nothing here calls a work-item backend, a file store, or a network. Every function
takes plain data — a body string, a comment snapshot, a work-item dict — and
returns plain data. The `workitem_host` backends and the `pdlc-*` scripts both
build on this so routing and rendering never diverge between them.
"""

from __future__ import annotations

import re
from datetime import datetime

from pdlc.domain.evidence import ReviewVerdict, parse_review
from pdlc.domain.lifecycle import MARKERS, PdlcError, require_marker
from pdlc.domain.workflow import Event, Gate, Lifecycle, PIPELINE_REGISTRY, Pipeline, State

# Work-item field names and the gate vocabulary

SKIP_FIELD_NAME = "Skipped States"
SLUG_FIELD_NAME = "Slug"
VALID_GATES = {
    "Pending", "Review Required", "Changes Required", "Decision Required",
    "CI Pending", "Approval Required", "Approved", "Stale",
}

# Delivery-task identity and tags

TASK_ID_PATTERN = re.compile(r"^WORK-\d+-(TASK-\d{3})")
TASK_TITLE_PATTERN = re.compile(r"^WORK-(\d+)-(TASK-\d{3})[ \t]*(.*)$")

# The tag stamped in front of a task's human title at creation, and the only
# thing that says which agent (UI vs. core) a task belongs to.
UI_TAG = "[UI]"
CORE_TAG = "[CORE]"

# A delivery task records its Technical Plan and its Implementation as
# standalone comments opening with these headings.
PLAN_COMMENT_HEADING = "## Technical Plan"
IMPLEMENTATION_COMMENT_HEADING = "## Implementation"


# Work-item field accessors -------------------------------------------------

def item_status(item: dict) -> str:
    return item.get("Status") or ""


def item_gate(item: dict) -> str:
    return item.get("Gate State") or ""


def item_issue(item: dict) -> str:
    number = item.get("content", {}).get("number", item.get("number"))
    return str(number) if number is not None else ""


def item_slug(item: dict) -> str:
    return item.get(SLUG_FIELD_NAME) or ""


def item_skipped_states(item: dict) -> str:
    return item.get(SKIP_FIELD_NAME) or ""


# True when `stage` appears in the item's declared Skipped States list.
def is_stage_skipped(item: dict, stage: str) -> bool:
    skipped = item_skipped_states(item)
    if not skipped:
        return False
    return stage in skipped.split(",")


def _workflow_state(item: dict, pipeline: Pipeline, status: str, gate: str) -> State:
    lifecycle = item.get("Lifecycle") or (Lifecycle.COMPLETED if status == pipeline.terminal_stage else Lifecycle.PLANNING)
    return State.parse(status, gate, lifecycle)


def blocked_reason(reason: str) -> str:
    """Add the required human stop for unsupported work-type routing."""
    if reason.startswith("unknown work type:") or reason.startswith("workflow unavailable for work type:"):
        detail = reason[:1].upper() + reason[1:]
        return f"stop here and let the user know this workflow is not supported. {detail}"
    return reason


def _blocked_due(item: dict, reason: str = "missing or unsupported work item state") -> dict:
    reason = blocked_reason(reason)
    status = item_status(item)
    gate = item_gate(item)
    notation = f"{status.replace(' ', '')}.{gate.replace(' ', '')}"
    return {
        "status": status,
        "gate": gate,
        "skipped_through": [],
        "action": "blocked",
        "autonomous": False,
        "reason": reason,
        "state": notation,
        "owner": f"blocked — {reason}",
    }


# Read-only routing view: looks ahead through consecutive declared-skipped
# stages the same way the mutating skip cascade does, but never posts a comment
# or writes state.
def due_next(item: dict) -> dict:
    try:
        pipeline = PIPELINE_REGISTRY.for_record(item)
        state = _workflow_state(item, pipeline, item_status(item), item_gate(item))
        pipeline.validate_state(state)
    except (TypeError, ValueError) as error:
        return _blocked_due(item, str(error))

    skipped_through: list[str] = []

    while state.gate in (Gate.PENDING, Gate.CHANGES_REQUIRED, Gate.STALE) and is_stage_skipped(item, state.stage):
        skipped_through.append(state.stage)
        try:
            state = pipeline.next_state(state, Event.SKIPPED)
        except (TypeError, ValueError):
            return _blocked_due(item)

    route = pipeline.route(state)
    owner = route.action.value
    if route.action.value == "human-input":
        owner = "human — invoke pdlc-write interactively"
    elif route.action.value == "human-approval":
        completion = pipeline.completion_policy
        owner = "human — pdlc post complete" if completion is not None and completion.is_boundary(state) else "human — pdlc post approve"
    elif route.action.value == "human-decision":
        owner = "human — resolve the blocking review decision (see the last PDLC-DECISION comment)"
    elif route.action.value == "pdlc-post-ci":
        owner = "pdlc post ci — record the registered PR stack's CI outcome"
    elif route.action.value == "none":
        owner = "none — record is Complete"
    elif route.action.value == "blocked":
        owner = "blocked — malformed or unsupported work item state"
    return {
        "status": state.stage,
        "gate": state.gate.value,
        "skipped_through": skipped_through,
        "action": route.action.value,
        "autonomous": route.autonomous,
        "reason": route.reason,
        "state": state.notation,
        "owner": owner,
        "reauthor_in_place": pipeline.stage(state.stage).reauthor_in_place,
    }


# Delivery-task comment classification ------------------------------------

# The newest comment that opens with `heading` (first non-empty line matches
# exactly), or None. Comments arrive oldest-first, so a re-planned or
# re-implemented task resolves to its latest note.
def latest_heading_comment(comments: list[str], heading: str) -> str | None:
    latest: str | None = None
    for comment in comments:
        for line in (comment or "").splitlines():
            if line.strip():
                if line.strip() == heading:
                    latest = comment
                break
    return latest


def latest_plan_comment(comments: list[str]) -> str | None:
    return latest_heading_comment(comments, PLAN_COMMENT_HEADING)


def has_implementation_comment(comments: list[str]) -> bool:
    return latest_heading_comment(comments, IMPLEMENTATION_COMMENT_HEADING) is not None


# Normalises a task's comment payload to a plain list of body strings,
# accepting the GraphQL `{nodes: [{body}]}` shape, a list of strings or
# `{body}` dicts, or a missing key.
def comment_bodies(raw: object) -> list[str]:
    if isinstance(raw, dict):
        raw = raw.get("nodes") or []
    if not isinstance(raw, list):
        return []
    return [item.get("body", "") if isinstance(item, dict) else str(item) for item in raw]


# Classifies one task's stage progress so callers read flags instead of
# interpreting bodies and comments themselves.
def classify_task(task: dict) -> dict:
    title = task.get("title") or ""
    comments = task.get("comments") or []
    plan_comment = latest_plan_comment(comments)
    has_implementation = has_implementation_comment(comments)
    title_match = TASK_TITLE_PATTERN.match(title)
    rest = title_match.group(3) if title_match else title
    return {
        **task,
        "hasPlan": plan_comment is not None,
        "hasImplementation": has_implementation,
        "planComment": plan_comment,
        "needsPlan": task["state"] == "OPEN" and not has_implementation,
        "isUI": rest.startswith(UI_TAG),
        # Attached pull requests come from the backend, which owns how they are
        # stored; classification never parses them out of the body.
        "prs": list(task.get("prs") or []),
    }


# Parent-body section editing --------------------------------------------

# Rewrites one `## <section>` block, replacing everything between that heading
# and the next level-2 heading with the fragment, and appending the section
# when it isn't present. Headings inside fenced code blocks are content.
def splice_section(body: str, section: str, fragment: str) -> str:
    heading = f"## {section}"
    fragment_lines = fragment.splitlines()
    body_lines = body.splitlines()

    fence = False
    skipping = False
    found = False
    out: list[str] = []

    for line in body_lines:
        probe = line.rstrip(" \t")
        if line.startswith("```") or line.startswith("~~~"):
            fence = not fence
        elif not fence and probe == heading:
            out.append(line)
            out.extend(fragment_lines)
            out.append("")
            found = True
            skipping = True
            continue
        elif skipping and not fence and line.startswith("## "):
            skipping = False
        if not skipping:
            out.append(line)

    if not found:
        if body_lines:
            out.append("")
        out.append(heading)
        out.extend(fragment_lines)

    return "\n".join(out) + "\n"


# Reads one `## <section>` block's content out of a body, without its heading.
def read_section(body: str, section: str) -> str:
    heading = f"## {section}"
    fence = False
    inside = False
    out: list[str] = []

    for line in body.splitlines():
        probe = line.rstrip(" \t")
        if line.startswith("```") or line.startswith("~~~"):
            fence = not fence
            if inside:
                out.append(line)
            continue
        if not fence and probe == heading:
            inside = True
            continue
        if inside and not fence and line.startswith("## "):
            inside = False
        if inside:
            out.append(line)

    return "\n".join(out) + ("\n" if out else "")


# Evidence comment / timeline parsing -----------------------------------

MARKER_PREFIX = re.compile(r"^PDLC-([A-Z]+)\b")
MARKER_LINE = re.compile(r"^PDLC-[A-Z]+\n\n?")


def compose_comment(marker: str | None, body: str) -> str:
    """Prefixes an evidence body with its `PDLC-<MARKER>` stamp, or returns it
    unchanged for a plain comment. Refuses a body that already carries one."""
    if marker is None:
        return body
    require_marker(marker)
    if body.startswith("PDLC-"):
        from pdlc.domain.lifecycle import PdlcError

        raise PdlcError("evidence already starts with a marker; write the body only")
    return f"PDLC-{marker}\n\n{body}"


# Every comment stamped with a given marker, oldest first.
def find_marked_comments(comments: list[dict], marker: str) -> list[dict]:
    require_marker(marker)
    prefix = f"PDLC-{marker}"
    matches = [comment for comment in comments if comment["body"].startswith(prefix)]
    matches.sort(key=lambda comment: comment["createdAt"])
    return matches


def verification_evidence_comments(comments: list[dict]) -> list[dict]:
    """Structured review evidence whose script-owned stage is Verification."""
    matches = []
    for comment in find_marked_comments(comments, "REVIEW"):
        try:
            review = parse_review(comment["body"])
        except PdlcError:
            continue
        if review.stage == "Verification":
            matches.append(comment)
    matches.sort(key=lambda comment: comment["createdAt"])
    return matches


# Every comment stamped with any marker, each tagged with which one, oldest
# first — the raw material for a stage-by-stage timeline.
def marked_comments(comments: list[dict]) -> list[dict]:
    tagged = []
    for comment in comments:
        match = MARKER_PREFIX.match(comment["body"])
        if match and match.group(1) in MARKERS:
            tagged.append({**comment, "marker": match.group(1)})
    tagged.sort(key=lambda comment: comment["createdAt"])
    return tagged


# Every comment carrying no `PDLC-*` marker — authored by a human or an
# outside bot, oldest first. These have no workflow meaning; the timeline
# (marker-only) hides them, so `pdlc inspect` surfaces them separately.
def user_comments(comments: list[dict]) -> list[dict]:
    plain = [comment for comment in comments if not MARKER_PREFIX.match(comment["body"])]
    plain.sort(key=lambda comment: comment["createdAt"])
    return plain


# A `## User Comments` section for the supplied snapshot, or `None` when there
# are no unmarked comments.
def user_comments_markdown(comments: list[dict]) -> str:
    plain = user_comments(comments)
    if not plain:
        return "## User Comments\n\nNone"
    lines = ["## User Comments"]
    for comment in plain:
        author = (comment.get("author") or {}).get("login", "unknown")
        when = _timeline_formatted_at(comment["createdAt"])
        body = comment["body"].strip()
        lines += ["", f"### @{author} — {when}", comment["url"], "", body]
    return "\n".join(lines)


# Localised to the machine's own time zone — the timeline is read
# interactively, not compared across machines.
def _timeline_formatted_at(created_at: str) -> str:
    stamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return f"{stamp.astimezone():%Y-%m-%d %H:%M %Z}".strip()


def _timeline_entry(comment: dict) -> str:
    author = (comment.get("author") or {}).get("login", "unknown")
    when = _timeline_formatted_at(comment["createdAt"])
    body = MARKER_LINE.sub("", comment["body"], count=1).strip()
    return f"## {comment['marker']} — {when} (@{author})\n{comment['url']}\n\n{body}"


# The first non-empty body line, heading marks stripped, trimmed to one line
# — enough for the caller to tell whether an entry is worth opening.
def _timeline_preview(comment: dict, limit: int = 140) -> str:
    body = MARKER_LINE.sub("", comment["body"], count=1).strip()
    for line in body.splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
    return ""


# The full chronological timeline text, plus a per-entry index giving each
# entry's 1-based inclusive line span within that text. `timeline_markdown`
# is this text; `timeline_compact` writes it to a file and prints the index.
def timeline_parts(comments: list[dict]) -> tuple[str, list[dict]]:
    tagged = marked_comments(comments)
    if not tagged:
        return "No PDLC evidence comments found\n", []

    lines = ["# Timeline", ""]
    index = []
    for position, comment in enumerate(tagged):
        if position:
            lines.append("")
        start = len(lines) + 1
        lines.extend(_timeline_entry(comment).split("\n"))
        index.append({
            "marker": comment["marker"],
            "when": _timeline_formatted_at(comment["createdAt"]),
            "author": (comment.get("author") or {}).get("login", "unknown"),
            "preview": _timeline_preview(comment),
            "start": start,
            "end": len(lines),
        })

    skipped = len(comments) - len(tagged)
    if skipped:
        lines += ["", "---", "", f"{skipped} comment(s) without a PDLC marker were skipped."]

    return "\n".join(lines) + "\n", index


# Renders every PDLC evidence comment as a chronological, stage-by-stage
# timeline from one supplied comment snapshot.
def timeline_markdown(comments: list[dict]) -> str:
    return timeline_parts(comments)[0]


# One block per evidence comment — marker, localised time, author, a
# one-line preview, and the line span to read from `file_path` (where the
# caller has already written `timeline_markdown`'s full text) for the whole
# comment. Keeps a long history out of stdout while staying navigable.
def timeline_compact(comments: list[dict], file_path: str) -> str:
    _, index = timeline_parts(comments)
    if not index:
        return "No PDLC evidence comments found\n"

    out = [f"# Timeline — {len(index)} evidence comment(s); full bodies in {file_path}", ""]
    for entry in index:
        out.append(f"## {entry['marker']} — {entry['when']} (@{entry['author']})")
        if entry["preview"]:
            out.append(f"   {entry['preview']}")
        out.append(f"   Read lines {entry['start']}-{entry['end']} in {file_path} for the full comment.")
        out.append("")

    skipped = len(comments) - len(index)
    if skipped:
        out.append(f"{skipped} comment(s) without a PDLC marker were skipped.")

    return "\n".join(out).rstrip("\n") + "\n"


# Rework-loop detection -------------------------------------------------


def review_rework_count(comments: list[dict], loop: str) -> int:
    """Count Verification Changes Required reviews that entered `loop`."""
    count = 0
    for comment in find_marked_comments(comments, "REVIEW"):
        try:
            review = parse_review(comment["body"])
        except PdlcError:
            continue
        if (
            review.stage == "Verification"
            and review.verdict == ReviewVerdict.CHANGES_REQUIRED
            and review.bounce is not None
            and review.loop == loop
        ):
            count += 1
    return count

# Stamped by pdlc post invalidate into the PDLC-INVALIDATED comment body.
_INVALIDATED_STAGE_LINE = re.compile(r"^Invalidated stage:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


# How many explicit driver invalidations targeted each stage. A comment without
# the script-owned line is ignored. Rework-loop accounting uses PDLC-REVIEW.
def invalidations_by_stage(comments: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for comment in find_marked_comments(comments, "INVALIDATED"):
        match = _INVALIDATED_STAGE_LINE.search(MARKER_LINE.sub("", comment["body"], count=1))
        if match:
            counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    return counts
