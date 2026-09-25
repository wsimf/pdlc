"""GitHub Project (v2) item access: field lookup, Issue-to-item resolution,
and single-select/text field writes that carry a PDLC record's Status, Gate
State, Lifecycle, Skipped States, and Slug.
"""

from __future__ import annotations

from functools import cache

from pdlc.hosts.lib.github.transport import (
    owner_repository,
    run_gh_json,
    run_graphql,
)
from pdlc.config import get_config
from pdlc.domain.lifecycle import NotFound, PdlcError, TransientError
from pdlc.domain.model import SKIP_FIELD_NAME, SLUG_FIELD_NAME, VALID_GATES
from pdlc.hosts.workitem_host.base import QueueItemSummary

# An Issue's Project item: id, Status/Gate State/Lifecycle single-select
# values, and the Issue's own number/title/url/body. `project { number }` lets
# the caller filter to the configured Project when an Issue has items on more
# than one.
ITEM_FOR_ISSUE_QUERY = """
query($owner: String!, $repo: String!, $issue: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $issue) {
      number
      title
      url
      body
      issueType { name }
      projectItems(first: 100) {
        nodes {
          id
          project { number }
          status: fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          gate: fieldValueByName(name: "Gate State") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          lifecycle: fieldValueByName(name: "Lifecycle") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          skippedStates: fieldValueByName(name: "Skipped States") {
            ... on ProjectV2ItemFieldTextValue { text }
          }
          slug: fieldValueByName(name: "Slug") {
            ... on ProjectV2ItemFieldTextValue { text }
          }
        }
      }
    }
  }
}
"""

QUEUE_ITEMS_QUERY = """
query($projectId: ID!, $after: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      items(first: 100, after: $after) {
        nodes {
          id
          content {
            __typename
            ... on Issue {
              number
              title
              url
              repository { nameWithOwner }
              issueType { name }
              assignees(first: 10) { nodes { login } }
            }
          }
          status: fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          gate: fieldValueByName(name: "Gate State") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          lifecycle: fieldValueByName(name: "Lifecycle") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          skippedStates: fieldValueByName(name: "Skipped States") {
            ... on ProjectV2ItemFieldTextValue { text }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

SET_STATE_MUTATION = """
mutation(
  $projectId: ID!, $itemId: ID!,
  $statusFieldId: ID!, $statusOptionId: String!,
  $gateFieldId: ID!, $gateOptionId: String!,
  $lifecycleFieldId: ID!, $lifecycleOptionId: String!
) {
  status: updateProjectV2ItemFieldValue(input: {
    projectId: $projectId, itemId: $itemId, fieldId: $statusFieldId,
    value: {singleSelectOptionId: $statusOptionId}
  }) { projectV2Item { id } }
  gate: updateProjectV2ItemFieldValue(input: {
    projectId: $projectId, itemId: $itemId, fieldId: $gateFieldId,
    value: {singleSelectOptionId: $gateOptionId}
  }) { projectV2Item { id } }
  lifecycle: updateProjectV2ItemFieldValue(input: {
    projectId: $projectId, itemId: $itemId, fieldId: $lifecycleFieldId,
    value: {singleSelectOptionId: $lifecycleOptionId}
  }) { projectV2Item { id } }
}
"""

ITEM_STATE_QUERY = """
query($itemId: ID!) {
  node(id: $itemId) {
    ... on ProjectV2Item {
      status: fieldValueByName(name: "Status") {
        ... on ProjectV2ItemFieldSingleSelectValue { name }
      }
      gate: fieldValueByName(name: "Gate State") {
        ... on ProjectV2ItemFieldSingleSelectValue { name }
      }
      lifecycle: fieldValueByName(name: "Lifecycle") {
        ... on ProjectV2ItemFieldSingleSelectValue { name }
      }
    }
  }
}
"""


def _normalize_work_type(value: object) -> str:
    """Return the stable lower-case work type, preserving missing values."""
    if value is None:
        return ""
    return str(value).strip().lower()


def _field_name(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return value.get("name") or ""


def _field_text(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return value.get("text") or ""


def _queue_summary(
    item: dict, repository: str | None, assignee: str | None = None
) -> QueueItemSummary | None:
    content = item.get("content") or {}
    content_type = content.get("__typename") or content.get("type")
    if (content_type is not None and content_type != "Issue") or not content.get("number"):
        return None
    item_repository = (content.get("repository") or {}).get("nameWithOwner")
    if repository and item_repository and item_repository.casefold() != repository.casefold():
        return None
    if assignee:
        logins = {
            (node or {}).get("login", "").casefold()
            for node in (content.get("assignees") or {}).get("nodes") or []
        }
        if assignee.casefold() not in logins:
            return None
    return {
        "id": item["id"],
        "content": {
            "number": int(content["number"]),
            "title": content.get("title") or "",
            "url": content.get("url") or "",
        },
        "Status": _field_name(item.get("status")) or item.get("Status") or item.get("status") or "",
        "Gate State": _field_name(item.get("gate")) or item.get("Gate State") or item.get("gateState") or "",
        "Lifecycle": _field_name(item.get("lifecycle")) or item.get("Lifecycle") or item.get("lifecycle") or "",
        SKIP_FIELD_NAME: _field_text(item.get("skippedStates")) or item.get(SKIP_FIELD_NAME) or "",
        "workType": _normalize_work_type((content.get("issueType") or {}).get("name") or item.get("workType")),
    }


def _resolved_assignee() -> str | None:
    """The configured `[backend.github] assigned_to` queue-scan filter as a
    login, or None when unset. `@me` (any case) resolves to the authenticated
    GitHub user so config need not hardcode a login."""
    value = (get_config().github_assigned_to or "").strip()
    if not value:
        return None
    if value.casefold() == "@me":
        return run_gh_json(["api", "user"])["login"]
    return value


# Returns only Issue summaries from the configured repository; drafts and
# cross-repository Project cards are not PDLC records for this backend. When
# `[backend.github] assigned_to` is set, only Issues assigned to that login.
def queue_items() -> list[QueueItemSummary]:
    config = get_config()
    assignee = _resolved_assignee()
    summaries: list[QueueItemSummary] = []
    after: str | None = None
    while True:
        variables = {"projectId": _project_id()}
        if after is not None:
            variables["after"] = after
        project = run_graphql(QUEUE_ITEMS_QUERY, **variables)["data"].get("node")
        if project is None:
            raise PdlcError(f"Project {config.project_owner}/{config.project_number} was not found")
        items = project["items"]
        summaries.extend(
            summary for item in items.get("nodes", [])
            if (summary := _queue_summary(item, config.repository, assignee)) is not None
        )
        page = items["pageInfo"]
        if not page["hasNextPage"]:
            return summaries
        after = page.get("endCursor")
        if not after:
            raise PdlcError("Project item pagination did not return an end cursor")


@cache
def project_fields() -> dict:
    config = get_config()
    return run_gh_json([
        "project", "field-list", config.project_number,
        "--owner", config.project_owner, "--format", "json",
    ])


def project_field(field: str) -> dict:
    for candidate in project_fields().get("fields", []):
        if candidate.get("name") == field:
            return candidate
    raise PdlcError(f"no such Project field: {field}")


def field_id(field: str) -> str:
    return project_field(field)["id"]


def option_id(field: str, value: str) -> str:
    for option in project_field(field).get("options", []):
        if option.get("name") == value:
            return option["id"]
    raise PdlcError(f"no option {value!r} on Project field {field!r}")


# Project-item identity

# Resolves an Issue number to its one Project item, live or from the fixture
# file. Comments are paginated separately by github_issues.comments_for_issue.
def item_for_issue(issue: str) -> dict:
    if not issue.isdigit():
        raise PdlcError(f"Issue number must be numeric: {issue}")

    config = get_config()
    owner, repository = owner_repository()
    data = run_graphql(ITEM_FOR_ISSUE_QUERY, owner=owner, repo=repository, issue=int(issue))
    issue_node = data["data"]["repository"]["issue"]
    if issue_node is None:
        raise NotFound(f"no GitHub Issue #{issue}")
    project_number = int(config.project_number)
    matches = [
        node for node in issue_node["projectItems"]["nodes"]
        if node["project"]["number"] == project_number
    ]
    if not matches:
        raise NotFound(f"Issue #{issue} has no item in the configured Project")
    if len(matches) != 1:
        raise PdlcError("expected exactly one Project item")
    node = matches[0]

    return {
        "id": node["id"],
        "content": {
            "number": issue_node["number"],
            "title": issue_node["title"],
            "url": issue_node["url"],
        },
        "issueBody": issue_node["body"],
        "workType": _normalize_work_type((issue_node.get("issueType") or {}).get("name")),
        "Status": (node.get("status") or {}).get("name") or "",
        "Gate State": (node.get("gate") or {}).get("name") or "",
        "Lifecycle": (node.get("lifecycle") or {}).get("name") or "",
        SKIP_FIELD_NAME: (node.get("skippedStates") or {}).get("text") or "",
        SLUG_FIELD_NAME: (node.get("slug") or {}).get("text") or "",
    }


def resolve_item(issue: str) -> dict:
    return item_for_issue(issue)


def issue_for_slug(slug: str) -> str:
    """Resolve an exact stable slug across every page of the configured Project."""
    query = """
    query($projectId: ID!, $after: String) {
      node(id: $projectId) {
        ... on ProjectV2 {
          items(first: 100, after: $after) {
            nodes {
              slug: fieldValueByName(name: "Slug") { ... on ProjectV2ItemFieldTextValue { text } }
              content { ... on Issue { number repository { nameWithOwner } } }
            }
            pageInfo { hasNextPage endCursor }
          }
        }
      }
    }
    """
    matches: list[str] = []
    after: str | None = None
    repository = get_config().repository or ""
    while True:
        variables = {"projectId": _project_id()}
        if after:
            variables["after"] = after
        project = (run_graphql(query, **variables).get("data") or {}).get("node")
        if not isinstance(project, dict):
            raise PdlcError("GitHub did not return the configured Project")
        items = project["items"]
        for item in items["nodes"]:
            content = item.get("content") or {}
            if (item.get("slug") or {}).get("text") != slug:
                continue
            if (content.get("repository") or {}).get("nameWithOwner", "").casefold() != repository.casefold():
                continue
            if content.get("number"):
                matches.append(str(content["number"]))
        page = items["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page.get("endCursor")
        if not cursor or cursor == after:
            raise PdlcError("Project slug pagination did not advance")
        after = cursor
    if not matches:
        raise NotFound(f"no PDLC record with slug: {slug}")
    if len(matches) != 1:
        raise PdlcError(f"slug is ambiguous: {slug}")
    return matches[0]


@cache
def _project_id() -> str:
    config = get_config()
    data = run_gh_json([
        "project", "view", config.project_number,
        "--owner", config.project_owner, "--format", "json",
    ])
    return data["id"]


def edit_single_select(item_id: str, field: str, value: str) -> dict:
    return run_gh_json([
        "project", "item-edit",
        "--id", item_id,
        "--project-id", _project_id(),
        "--field-id", field_id(field),
        "--single-select-option-id", option_id(field, value),
        "--format", "json",
    ])


def _edit_text_field(item_id: str, field: str, value: str) -> dict:
    return run_gh_json([
        "project", "item-edit",
        "--id", item_id,
        "--project-id", _project_id(),
        "--field-id", field_id(field),
        "--text", value,
        "--format", "json",
    ])


# Pre-declared skip list (see pdlc post skip)

# Overwrites the Skipped States text field with an explicit comma-joined
# value; callers own list validation, merging, and dedup.
def set_skipped_states(item_id: str, value: str) -> dict:
    return _edit_text_field(item_id, SKIP_FIELD_NAME, value)


# Stable slug (see pdlc post write)

# Sets the Slug text field once, at record creation; never overwritten after.
def set_slug(item_id: str, value: str) -> dict:
    return _edit_text_field(item_id, SLUG_FIELD_NAME, value)


# Project-state transitions

def _state_for_item(item_id: str) -> tuple[str, str, str]:
    response = run_graphql(ITEM_STATE_QUERY, itemId=item_id)
    data = (response.get("data") or {}).get("node")
    if not isinstance(data, dict):
        raise PdlcError(f"GitHub returned no Project item state for {item_id}")
    return (
        (data.get("status") or {}).get("name") or "",
        (data.get("gate") or {}).get("name") or "",
        (data.get("lifecycle") or {}).get("name") or "",
    )


def _set_state_once(item_id: str, status: str, gate: str, lifecycle: str) -> None:
    response = run_graphql(
        SET_STATE_MUTATION,
        projectId=_project_id(),
        itemId=item_id,
        statusFieldId=field_id("Status"),
        statusOptionId=option_id("Status", status),
        gateFieldId=field_id("Gate State"),
        gateOptionId=option_id("Gate State", gate),
        lifecycleFieldId=field_id("Lifecycle"),
        lifecycleOptionId=option_id("Lifecycle", lifecycle),
    )
    data = response.get("data") or {}
    if not all(((data.get(alias) or {}).get("projectV2Item") or {}).get("id") == item_id for alias in ("status", "gate", "lifecycle")):
        raise PdlcError("GitHub returned an incomplete Project state transition")

# Submits the three fields in one GraphQL mutation request. GitHub still
# updates each field independently, so the result is re-read and one
# idempotent reconciliation attempt is made before failure is reported.
def set_state(item_id: str, status: str, gate: str, lifecycle: str) -> None:
    if gate not in VALID_GATES:
        raise PdlcError(f"invalid Gate State: {gate}")
    expected = (status, gate, lifecycle)
    actual: tuple[str, str, str] | None = None
    last_error: PdlcError | None = None

    for _ in range(2):
        try:
            _set_state_once(item_id, *expected)
        except PdlcError as error:
            last_error = error
        try:
            actual = _state_for_item(item_id)
        except PdlcError as error:
            last_error = error
            continue
        if actual == expected:
            return

    detail = f"; last error: {last_error}" if last_error else ""
    message = f"Project state transition did not settle at {status} / {gate} / {lifecycle}; observed {actual}{detail}"
    # Keep a transient cause transient so the caller still reports it as retryable.
    if isinstance(last_error, TransientError):
        raise TransientError(message, attempts=last_error.attempts)
    raise PdlcError(message)
