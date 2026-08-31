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

from pdlc.domain.lifecycle import (
    MARKERS,
    action_for,
    next_status_for,
    require_marker,
    state_after_skip,
    state_notation,
)

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


# Read-only routing view: looks ahead through consecutive declared-skipped
# stages the same way the mutating skip cascade does, but never posts a comment
# or writes state.
def due_next(item: dict) -> dict:
    status = item_status(item)
    gate = item_gate(item)
    skipped_through: list[str] = []

    while status != "Complete" and gate in ("Pending", "Changes Required", "Stale") and is_stage_skipped(item, status):
        skipped_through.append(status)
        status, gate = state_after_skip(status)

    action, autonomous, reason = action_for(status, gate)
    return {
        "status": status,
        "gate": gate,
        "skipped_through": skipped_through,
        "action": action,
        "autonomous": autonomous,
        "reason": reason,
        "state": state_notation(status, gate),
        "next_state": next_status_for(status, gate),
    }


# Delivery-task metadata block ------------------------------------------

# A machine-owned HTML comment pinned to the very top of a delivery task's
# body. Commands record data here that must outlive re-planning without
# touching the human-authored body below it — today just the task's pull
# request numbers. Invisible in rendered Markdown. Everything after the
# closing `-->` (and one blank line) is the untouched task body.
#
# Each `key: value` line's value is whitespace-split into a token list with no
# quoting or escaping — fine for the numeric/identifier tokens stored today,
# not a general key-value store.
_TASK_META_OPEN = "<!-- pdlc:meta"
_TASK_META_RE = re.compile(r"\A<!-- pdlc:meta\n(.*?)\n-->\n?", re.DOTALL)


def read_task_meta(body: str) -> dict[str, list[str]]:
    match = _TASK_META_RE.match(body or "")
    if not match:
        return {}
    meta: dict[str, list[str]] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, rest = line.partition(":")
            meta[key.strip()] = rest.split()
    return meta


def strip_task_meta(body: str) -> str:
    """The task body with any leading metadata block removed."""
    return _TASK_META_RE.sub("", body or "", count=1).lstrip("\n")


def write_task_meta(body: str, meta: dict[str, list[str]]) -> str:
    """`body` with its metadata block replaced by `meta` (keys with an empty
    value list are dropped; an empty `meta` removes the block entirely)."""
    clean = strip_task_meta(body)
    entries = {key: list(values) for key, values in meta.items() if values}
    if not entries:
        return clean
    lines = "\n".join(f"{key}: {' '.join(values)}" for key, values in entries.items())
    return f"{_TASK_META_OPEN}\n{lines}\n-->\n\n{clean}"


def task_prs(body: str) -> list[int]:
    """The pull-request numbers registered on a task, ascending."""
    numbers = [int(value) for value in read_task_meta(body).get("prs", []) if value.isdigit()]
    return sorted(set(numbers))


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
        "prs": task_prs(task.get("body") or ""),
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

# Stamped by pdlc post invalidate / pdlc post verify --bounce into the
# PDLC-INVALIDATED comment body, so the rework loop is reconstructable from
# comment history with no extra work-item state.
_INVALIDATED_STAGE_LINE = re.compile(r"^Invalidated stage:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


# How many times each stage was returned to Stale, read from the
# `Invalidated stage:` line of each PDLC-INVALIDATED comment. A comment without
# that line (written before the stamp existed) is not counted. The churn gate
# sums these to decide whether to auto-clear the Implementation/Testing approval.
def invalidations_by_stage(comments: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for comment in find_marked_comments(comments, "INVALIDATED"):
        match = _INVALIDATED_STAGE_LINE.search(MARKER_LINE.sub("", comment["body"], count=1))
        if match:
            counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    return counts
