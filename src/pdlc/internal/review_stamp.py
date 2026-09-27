"""The local files a stage's reviewer was handed, kept so the stage lands only
what was reviewed and a reviewer's edits can be undone.

One JSON stamp per work item and stage sits in the work-item cache:
`{"stage", "workItem", "files": {absolute path: content}}`. The reviewer's
brief command writes it; the planner's brief command restores any edit made
since and clears it, because a new planning pass begins; the stage's post
command restores any edit made since, and a real landing requires the stamp to
cover the manifest it lands, then clears it.
"""

from __future__ import annotations

import json
from pathlib import Path

from pdlc.domain.lifecycle import PdlcError
from pdlc.internal.scratch import cache_file, replace_cache_file


def _stamp_path(work_item: str, stage: str) -> Path:
    return cache_file(work_item, f"{stage.lower().replace(' ', '-')}-review")


def _key(path: str | Path) -> str:
    return str(Path(path).resolve())


def _read(work_item: str, stage: str) -> dict[str, str] | None:
    path = _stamp_path(work_item, stage)
    if not path.exists():
        return None
    try:
        stamp = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PdlcError(f"cannot read the review stamp {path}: {error}; delete it and review again") from None
    files = stamp.get("files") if isinstance(stamp, dict) else None
    valid = (
        isinstance(files, dict)
        and stamp.get("stage") == stage
        and stamp.get("workItem") == str(work_item)
        and all(isinstance(key, str) and isinstance(value, str) for key, value in files.items())
    )
    if not valid:
        raise PdlcError(f"the review stamp {path} is not a {stage} stamp for work item {work_item}; delete it and review again")
    return files


def _save(work_item: str, stage: str, files: dict[str, str]) -> None:
    stamp = {"stage": stage, "workItem": str(work_item), "files": files}
    replace_cache_file(_stamp_path(work_item, stage), json.dumps(stamp, indent=2, ensure_ascii=False) + "\n")


def write_stamp(work_item: str, stage: str, paths: list[Path]) -> None:
    """Record the exact files handed to the reviewer."""
    _save(work_item, stage, {_key(path): Path(path).read_text(encoding="utf-8") for path in paths})


def refresh_stamp(work_item: str, stage: str, path: Path) -> None:
    """Carry a command's own rewrite of a reviewed file into the stamp."""
    files = _read(work_item, stage)
    if files is not None and _key(path) in files:
        files[_key(path)] = Path(path).read_text(encoding="utf-8")
        _save(work_item, stage, files)


def clear_stamp(work_item: str, stage: str) -> None:
    _stamp_path(work_item, stage).unlink(missing_ok=True)


def _rejected_copy(path: Path) -> Path:
    return path.with_name(f"{path.stem}.rejected{path.suffix}")


def restore_reviewed(work_item: str, stage: str, rereview: str, replan: str) -> None:
    """Undo any change to a reviewed file, then refuse so the review is redone.

    With no stamp there is nothing reviewed to protect. An edited file is kept
    beside the restored one as `<name>.rejected<suffix>`, so nothing is lost.
    `rereview` and `replan` are the reviewer's and planner's brief commands.
    """
    files = _read(work_item, stage)
    if files is None:
        return
    restored: list[str] = []
    for name, reviewed in files.items():
        path = Path(name)
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == reviewed:
            continue
        if current is not None:
            _rejected_copy(path).write_text(current, encoding="utf-8")
        path.write_text(reviewed, encoding="utf-8")
        restored.append(name)
    if restored:
        listed = "\n".join(f"  - {name}" for name in restored)
        raise PdlcError(
            "the files handed to the reviewer changed after its brief was written, and no planning pass ran since:\n"
            f"{listed}\n"
            "The reviewer must not edit the files it reviews, so its verdict may describe content the planner never wrote.\n"
            "pdlc restored each file to the version the reviewer was given and kept the edited copy beside it as"
            " <name>.rejected<suffix>. Nothing was written to the record.\n"
            "Discard that review's verdict and findings, then re-dispatch the reviewer with a fresh brief:\n"
            f"  {rereview}\n"
            "If the planner made these edits, it did so without a fresh planning brief: start every planning pass"
            f" with `{replan}`, then carry the edits over from the .rejected copies."
        )


def require_reviewed(work_item: str, stage: str, manifest: Path, rereview: str) -> None:
    """Refuse a landing whose manifest the reviewer was not handed as it is now.

    Call after `restore_reviewed`, which has already undone any edit made
    since the review, so a stamp covering the manifest covers its files too.
    """
    files = _read(work_item, stage)
    if files is None or _key(manifest) not in files:
        raise PdlcError(
            f"refusing to land: {manifest} has not been reviewed since its last planning pass.\n"
            "Only reviewed files can land. Dispatch the reviewer on this manifest, and post again only after a clean verdict:\n"
            f"  {rereview}\n"
            "Nothing was written to the record."
        )
