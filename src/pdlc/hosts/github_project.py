"""GitHub Project (v2) item access: field lookup, Issue-to-item resolution,
and single-select/text field writes that carry a PDLC record's Status, Gate
State, Lifecycle, Skipped States, and Slug.
"""

from __future__ import annotations

import json
import os
from functools import cache

from pdlc.hosts.github_common import (
    owner_repository,
    run_gh_json,
    run_graphql,
)
from pdlc.config import get_config
from pdlc.domain.lifecycle import PdlcError
from pdlc.domain.model import SKIP_FIELD_NAME, SLUG_FIELD_NAME, VALID_GATES

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


def _normalize_project_item(item: dict) -> dict:
    fields = item.get("fields") or {}
    return {
        **item,
        "Status": item.get("Status") or item.get("status") or fields.get("Status") or "",
        "Gate State": (
            item.get("Gate State")
            or item.get("gate State")
            or item.get("gateState")
            or fields.get("Gate State")
            or ""
        ),
        "Lifecycle": item.get("Lifecycle") or item.get("lifecycle") or fields.get("Lifecycle") or "",
        SKIP_FIELD_NAME: (
            item.get(SKIP_FIELD_NAME)
            or item.get("skipped States")
            or fields.get(SKIP_FIELD_NAME)
            or ""
        ),
        SLUG_FIELD_NAME: item.get(SLUG_FIELD_NAME) or item.get("slug") or fields.get(SLUG_FIELD_NAME) or "",
    }


# PDLC_ITEMS_FILE lets tests/fixtures stand in for a live `gh project` call.
def project_items() -> dict:
    config = get_config()
    fixture = config.items_file
    if fixture:
        with open(fixture) as handle:
            result = json.load(handle)
    else:
        result = run_gh_json([
            "project", "item-list", config.project_number,
            "--owner", config.project_owner, "--format", "json", "--limit", "1000",
        ])
    return {**result, "items": [_normalize_project_item(item) for item in result.get("items", [])]}


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
    if config.items_file:
        matches = [
            item for item in project_items().get("items", [])
            if str(item.get("content", {}).get("number", item.get("number"))) == issue
        ]
        if len(matches) != 1:
            raise PdlcError("expected exactly one Project item")
        return _normalize_project_item(matches[0])

    owner, repository = owner_repository()
    data = run_graphql(ITEM_FOR_ISSUE_QUERY, owner=owner, repo=repository, issue=int(issue))
    issue_node = data["data"]["repository"]["issue"]
    project_number = int(config.project_number)
    matches = [
        node for node in issue_node["projectItems"]["nodes"]
        if node["project"]["number"] == project_number
    ]
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
        "Status": (node.get("status") or {}).get("name"),
        "Gate State": (node.get("gate") or {}).get("name"),
        "Lifecycle": (node.get("lifecycle") or {}).get("name"),
        SKIP_FIELD_NAME: (node.get("skippedStates") or {}).get("text") or "",
        SLUG_FIELD_NAME: (node.get("slug") or {}).get("text") or "",
    }


def resolve_item(issue: str) -> dict:
    return item_for_issue(issue)


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
    raise PdlcError(
        f"Project state transition did not settle at {status} / {gate} / {lifecycle}; observed {actual}{detail}"
    )
