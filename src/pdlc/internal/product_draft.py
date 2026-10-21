"""The CLI-owned Product draft, its review stamp, and its two findings files.

`pdlc prompt product-writer` creates the draft at a fixed cache path keyed by
the work item number, or by `new-<slug>` before a record exists; every later
command takes that path and recovers the key from it, so the reviewers, the
spike, and `pdlc post write` all act on the one file. The stamp records what
each step saw (see `pdlc.domain.product_draft`), the attachments file the
local files the driver supplied for it, and a successful landing deletes the
draft, the stamp, the attachments file, and both findings files.
"""

from __future__ import annotations

import json
from pathlib import Path

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.attachment_host import get_host
from pdlc.internal.attachments import attachments_list, validate_attachments
from pdlc.domain.product_draft import Phase, Stamp, land_problems, phase, review_verdict, subsection, TECHNICAL_APPROACH
from pdlc.internal.review_stamp import findings_path
from pdlc.internal.scratch import cache_file, replace_cache_file
from pdlc.templates.template import load_template, template_problems

PRODUCT_REVIEW = "Product"
TECHNICAL_REVIEW = "Technical"
APPROACH_TEMPLATE = "technical-approach"


def key_for(work_item: str | None, slug: str | None) -> str:
    """The cache key: the work item number, or `new-<slug>` before a record exists."""
    if work_item:
        return str(work_item)
    if not slug:
        raise PdlcError("a Product draft needs a work item number or a slug")
    return f"new-{slug}"


def work_item_of(key: str) -> str | None:
    return key if key.isdigit() else None


def slug_of(key: str) -> str | None:
    return key.removeprefix("new-") if key.startswith("new-") else None


def draft_path(key: str) -> Path:
    return cache_file(key, "product-draft", ".md")


def _stamp_path(key: str) -> Path:
    return cache_file(key, "product-review")


def _attachments_path(key: str) -> Path:
    return cache_file(key, "product-attachments")


def product_findings_path(key: str) -> Path:
    return findings_path(key, PRODUCT_REVIEW)


def technical_findings_path(key: str) -> Path:
    return findings_path(key, TECHNICAL_REVIEW)


def key_of_draft(path: str | Path) -> str:
    """The key of a draft `pdlc prompt product-writer` created, refusing any other file."""
    resolved = Path(path).expanduser().resolve()
    key = resolved.parent.name
    if not key or draft_path(key).resolve() != resolved:
        raise PdlcError(
            f"{path} is not a Product draft created by `pdlc prompt product-writer`; run that command and use"
            " the draft path its brief names"
        )
    if not resolved.is_file():
        raise PdlcError(f"the Product draft {path} does not exist; run `pdlc prompt product-writer` to create it")
    return key


def read_stamp(key: str) -> Stamp:
    path = _stamp_path(key)
    if not path.exists():
        return Stamp()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PdlcError(f"cannot read the Product review stamp {path}: {error}; delete it and review again") from None
    if not isinstance(data, dict) or data.get("key") != key:
        raise PdlcError(f"the review stamp {path} is not a Product stamp for {key}; delete it and review again")
    values = {name: data.get(name) for name in ("product", "spiked", "technical")}
    if not all(value is None or isinstance(value, str) for value in values.values()):
        raise PdlcError(f"the review stamp {path} is malformed; delete it and review again")
    return Stamp(**values)


def write_stamp(key: str, stamp: Stamp) -> None:
    data = {"key": key, "product": stamp.product, "spiked": stamp.spiked, "technical": stamp.technical}
    replace_cache_file(_stamp_path(key), json.dumps(data, indent=2) + "\n")


def read_attachments(key: str) -> list[dict]:
    """The local files recorded for the draft, each `{path, description}`,
    refusing when one has since moved or emptied: landing would fail on it."""
    path = _attachments_path(key)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PdlcError(f"cannot read the Product draft's attachments {path}: {error}; delete it and pass them again") from None
    if not isinstance(data, list) or not all(isinstance(entry, dict) and isinstance(entry.get("path"), str) for entry in data):
        raise PdlcError(f"the Product draft's attachments {path} are malformed; delete it and pass them again")
    try:
        validate_attachments(data)
    except PdlcError as error:
        raise PdlcError(f"{error}; restore it, or pass --restart and start the draft again") from None
    return data


def add_attachments(key: str, inputs: list[dict]) -> list[dict]:
    """Record `inputs` alongside those already recorded; passing a path again
    replaces its description. Validates every input before writing any."""
    added = [
        {"path": str(entry["path"].resolve()), "description": entry["description"]}
        for entry in validate_attachments(inputs)
    ]
    if not added:
        return read_attachments(key)
    paths = {entry["path"] for entry in added}
    recorded = [entry for entry in read_attachments(key) if entry["path"] not in paths] + added
    replace_cache_file(_attachments_path(key), json.dumps(recorded, indent=2) + "\n")
    return recorded


def attachments_text(key: str) -> str:
    """The numbered list of the draft's attachments for a brief: those already
    on the record, then those recorded for landing; empty when there are none."""
    work_item = work_item_of(key)
    landed = get_host().list_for(work_item) if work_item else []
    return attachments_list(landed + read_attachments(key))


def findings_verdict(path: Path) -> str | None:
    return review_verdict(path.read_text(encoding="utf-8")) if path.is_file() else None


def current_phase(key: str) -> Phase:
    draft = draft_path(key).read_text(encoding="utf-8")
    return phase(
        draft, read_stamp(key),
        findings_verdict(product_findings_path(key)), findings_verdict(technical_findings_path(key)),
    )


def draft_problems(draft: str) -> list[str]:
    """Everything that keeps `draft` from landing as it stands, stamps aside."""
    problems = land_problems(draft)
    approach = subsection(draft, TECHNICAL_APPROACH)
    if approach:
        problems.extend(
            f"{problem} in ### {TECHNICAL_APPROACH}"
            for problem in template_problems(load_template(APPROACH_TEMPLATE), approach)
        )
    return problems


def clear(key: str) -> None:
    """Delete the draft, its stamp, its attachments file, and both findings files."""
    paths = (draft_path(key), _stamp_path(key), _attachments_path(key), product_findings_path(key), technical_findings_path(key))
    for path in paths:
        path.unlink(missing_ok=True)
