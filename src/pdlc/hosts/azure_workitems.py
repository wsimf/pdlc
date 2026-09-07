"""Azure DevOps Boards transport for the Azure work-item backend: work-item
reads and field writes, WIQL queries, parent/child links, and discussion
comments. Everything here is reached only through `workitem_host/azure.py`.

Large text fields default to HTML when written through the API, which renders
Markdown literally in the Azure UI. Creation therefore goes through
`az devops invoke` so it can carry the `multilineFieldsFormat` operation that
`az boards` has no flag for; the choice is per work item, one-way, and sticky,
so every later `az boards work-item update` keeps rendering Markdown. Comments
carry their own per-comment format and so are posted the same way.

PDLC state lives in custom fields on the work-item type, added once by an org
admin through an inherited process (see "Azure Boards fields" in README.md).
This module treats them as a precondition and never creates or checks them —
Azure validates picklist values server-side and names the offending field and
value in its error, which is surfaced unchanged.
"""

from __future__ import annotations

from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.azure_common import (
    PATCH_MEDIA_TYPE,
    WIT_API_VERSION,
    az_invoke,
    azure_config,
    org_args,
    project_args,
    run_az_json,
)

# The custom fields carrying PDLC record state. Azure derives the `Custom.`
# prefix from the display name an admin types, so `PdlcStatus` is stored and
# queried as `Custom.PdlcStatus`.
STATUS_FIELD = "Custom.PdlcStatus"
GATE_FIELD = "Custom.PdlcGateState"
LIFECYCLE_FIELD = "Custom.PdlcLifecycle"
SKIPPED_FIELD = "Custom.PdlcSkippedStates"
SLUG_FIELD = "Custom.PdlcSlug"
# Space-separated pull-request numbers. Deliberately not an `ArtifactLink`
# relation: that type addresses Azure Repos pull requests only and cannot
# reference the GitHub pull requests this backend is paired with.
PRS_FIELD = "Custom.PdlcPrs"

TITLE_FIELD = "System.Title"
DESCRIPTION_FIELD = "System.Description"
STATE_FIELD = "System.State"
TYPE_FIELD = "System.WorkItemType"
PARENT_FIELD = "System.Parent"

TASK_TYPE = "Task"

# The fields a queue scan needs. WIQL returns exactly what it selects, so this
# one query is the whole scan — no follow-up per-item read.
QUEUE_FIELDS = (
    "System.Id", TITLE_FIELD, STATUS_FIELD, GATE_FIELD,
    LIFECYCLE_FIELD, SKIPPED_FIELD, SLUG_FIELD, TYPE_FIELD,
)

# The fields a delivery task needs; its comments are fetched separately.
# `System.Description` is a long-text field but WIQL returns it fine, which
# keeps the upsert's body comparison honest — without it every re-run would
# see an empty stored body and rewrite the task.
TASK_FIELDS = ("System.Id", TITLE_FIELD, STATE_FIELD, DESCRIPTION_FIELD, PRS_FIELD)


def item_url(item_id: int | str) -> str:
    """The human-facing board URL. `show` returns an `_apis/...` URL instead,
    which is useless in evidence a person reads."""
    organization, project = azure_config()
    return f"{organization}/{project}/_workitems/edit/{item_id}"


def numeric(ref: str, label: str = "work item id") -> int:
    if not str(ref).isdigit():
        raise PdlcError(f"{label} must be numeric: {ref}")
    return int(ref)


# --- reads ---

def show(item_id: int | str) -> dict:
    item = run_az_json(["boards", "work-item", "show", *org_args(), "--id", str(item_id)])
    if not item:
        raise PdlcError(f"no Azure work item #{item_id}")
    return item


def query(wiql: str) -> list[dict]:
    """Every work item matching `wiql`, carrying exactly the selected fields."""
    return run_az_json(["boards", "query", *project_args(), "--wiql", wiql]) or []


def _select(fields: tuple[str, ...], where: str) -> str:
    _, project = azure_config()
    columns = ",".join(f"[{field}]" for field in fields)
    return (
        f"SELECT {columns} FROM workitems "
        f"WHERE [System.TeamProject] = '{project}' AND {where}"
    )


def records(record_type: str) -> list[dict]:
    """Every registered PDLC record — one carrying a Slug — on the board."""
    return query(_select(
        QUEUE_FIELDS,
        f"[{TYPE_FIELD}] = '{record_type}' AND [{SLUG_FIELD}] <> ''",
    ))


def by_slug(slug: str, record_type: str) -> dict:
    """The single record carrying `slug`. Never guesses between duplicates."""
    if "'" in slug:
        raise PdlcError(f"slug must not contain a quote: {slug}")
    matches = query(_select(
        ("System.Id",),
        f"[{TYPE_FIELD}] = '{record_type}' AND [{SLUG_FIELD}] = '{slug}'",
    ))
    if not matches:
        raise PdlcError(f"no PDLC record with slug: {slug}")
    if len(matches) > 1:
        raise PdlcError(f"slug is ambiguous: {slug}")
    return show(matches[0]["id"])


def children(parent_id: int | str) -> list[dict]:
    """The record's child work items, in board order."""
    return query(_select(TASK_FIELDS, f"[{PARENT_FIELD}] = {numeric(parent_id)}"))


# --- writes ---

def update(item_id: int | str, fields: dict[str, str] | None = None, *, state: str | None = None) -> dict:
    """Set any number of fields, and optionally the work-item state, in one
    PATCH — Azure applies them atomically."""
    args = ["boards", "work-item", "update", *org_args(), "--id", str(item_id)]
    if state is not None:
        args += ["--state", state]
    if fields:
        args += ["-f", *(f"{name}={value}" for name, value in fields.items())]
    return run_az_json(args) or {}


def create(work_item_type: str, title: str, fields: dict[str, str] | None = None) -> dict:
    """Create a work item with its description rendered as Markdown.

    Not `az boards work-item create`: that command cannot set
    `multilineFieldsFormat`, so its work items render `##` and `-` literally
    forever — the format is one-way and cannot be repaired by a later update
    through any `az` path.
    """
    _, project = azure_config()
    operations: list[dict] = [{"op": "add", "path": f"/fields/{TITLE_FIELD}", "value": title}]
    operations += [
        {"op": "add", "path": f"/fields/{name}", "value": value}
        for name, value in (fields or {}).items()
    ]
    if fields and DESCRIPTION_FIELD in fields:
        operations.append({
            "op": "add",
            "path": f"/multilineFieldsFormat/{DESCRIPTION_FIELD}",
            "value": "Markdown",
        })
    item = az_invoke(
        "wit", "workitems",
        route_parameters={"project": project, "type": work_item_type},
        http_method="POST", media_type=PATCH_MEDIA_TYPE,
        api_version=WIT_API_VERSION, body=operations,
    )
    if not item or "id" not in item:
        raise PdlcError(f"Azure did not return a work item id for: {title}")
    return item


def add_parent(child_id: int | str, parent_id: int | str) -> None:
    """Link child→parent. The relation is first-class and queryable back
    through `System.Parent`, so the hierarchy needs no title convention to be
    machine-readable — the `WORK-<n>-TASK-NNN` prefix carries task identity
    only."""
    run_az_json([
        "boards", "work-item", "relation", "add", *org_args(),
        "--id", str(child_id), "--relation-type", "parent",
        "--target-id", str(parent_id),
    ])


# --- comments ---

def comments(item_id: int | str) -> list[dict]:
    """Every discussion comment, oldest first. `az` has no verb for this, and
    `work-item show --expand all` omits comments, so it is the one read that
    goes through `devops invoke`."""
    _, project = azure_config()
    collected: list[dict] = []
    parameters: dict[str, str] = {}
    while True:
        page = az_invoke(
            "wit", "comments",
            route_parameters={"project": project, "workItemId": str(item_id)},
            query_parameters=parameters or None,
        ) or {}
        collected.extend(page.get("comments") or [])
        token = page.get("continuationToken")
        if not token:
            break
        parameters = {"continuationToken": token}
    return sorted(collected, key=lambda comment: comment.get("id") or 0)


def comments_page(item_id: int | str, page: int = 1, per_page: int = 100) -> dict:
    """Return one newest-first comments page using Azure continuation tokens.

    Azure's comments endpoint supplies the exact ``totalCount`` alongside each
    bounded response. Replaying the token chain is necessary for page numbers
    beyond the first, but each request remains capped at the caller's page
    size and no full history is materialized.
    """
    if page < 1 or per_page != 100:
        raise PdlcError("comments page must be >= 1 and use 100 comments per page")
    _, project = azure_config()
    token: str | None = None
    result: dict = {}
    for index in range(page):
        parameters = {"$top": str(per_page), "order": "desc"}
        if token:
            parameters["continuationToken"] = token
        result = az_invoke(
            "wit", "comments",
            route_parameters={"project": project, "workItemId": str(item_id)},
            query_parameters=parameters,
        ) or {}
        token = result.get("continuationToken")
        if index < page - 1 and not token:
            return {"comments": [], "totalCount": result.get("totalCount", 0)}
    return result


def post_comment(item_id: int | str, body: str) -> str:
    """Append one comment verbatim, as Markdown, and return a reference to it.

    Not `az boards work-item update --discussion`: that posts `format=html`,
    so an evidence comment's headings and lists render as literal punctuation.
    Comment format is per comment, not sticky like a work item's description,
    so every comment has to take this path.
    """
    _, project = azure_config()
    comment = az_invoke(
        "wit", "comments",
        route_parameters={"project": project, "workItemId": str(item_id)},
        query_parameters={"format": "markdown"},
        http_method="POST", body={"text": body},
    ) or {}
    identifier = comment.get("id")
    return f"{item_url(item_id)}?discussionId={identifier}" if identifier else item_url(item_id)
