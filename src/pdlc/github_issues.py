"""GitHub Issues transport for the GitHub work-item backend: delivery
sub-issues (read, upsert, link) and evidence comments. Pull requests belong
to `code_host`; body section editing and evidence parsing are pure and live
in `pdlc_model`. Everything here is reached only through
`workitem_host/github.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pdlc.github_common import (
    body_file,
    neutralize_refs,
    owner_repository,
    repo_args,
    run_gh,
    run_gh_json,
    run_graphql,
)
from pdlc.github_project import item_for_issue
from pdlc.pdlc_common import PdlcError, read_body_source
from pdlc.pdlc_model import (
    TASK_ID_PATTERN,
    TASK_TITLE_PATTERN,
    comment_bodies,
    compose_comment,
)

# Delivery task sub-issues of a parent Issue: enough to match one to its stable
# WORK-NNN-TASK-NNN identity, to check whether any are still open, and to
# derive its planning and implementation progress from its comments.
SUBISSUES_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      subIssues(first: 100) {
        nodes {
          number title url state body
          comments(first: 100) { nodes { body } }
        }
      }
    }
  }
}
"""


def link_subissue(parent: int | str, child: int | str) -> None:
    link_subissues(parent, [child])


def _link_subissues_once(parent: int | str, children: list[int | str]) -> None:
    if not children:
        return
    numbers = [str(parent), *(str(child) for child in children)]
    if not all(number.isdigit() for number in numbers):
        raise PdlcError("sub-issue numbers must be numeric")

    owner, repository = owner_repository()
    selections = "\n".join(
        f"issue{index}: issue(number: {int(number)}) {{ id }}"
        for index, number in enumerate(numbers)
    )
    query = f"""
    query($owner: String!, $repo: String!) {{
      repository(owner: $owner, name: $repo) {{
        {selections}
      }}
    }}
    """
    issues = run_graphql(query, owner=owner, repo=repository)["data"]["repository"]
    node_ids = [(issues[f"issue{index}"] or {}).get("id") for index in range(len(numbers))]
    if any(node_id is None for node_id in node_ids):
        raise PdlcError("one or more sub-issue nodes do not exist")

    declarations = ", ".join(["$parentId: ID!", *(f"$child{index}: ID!" for index in range(len(children)))])
    mutations = "\n".join(
        f"link{index}: addSubIssue(input: {{issueId: $parentId, subIssueId: $child{index}}}) {{ issue {{ id }} }}"
        for index in range(len(children))
    )
    mutation = f"mutation({declarations}) {{\n{mutations}\n}}"
    variables = {"parentId": node_ids[0]}
    variables.update({f"child{index}": node_id for index, node_id in enumerate(node_ids[1:])})
    response = run_graphql(mutation, **variables)
    data = response.get("data") or {}
    if not all(((data.get(f"link{index}") or {}).get("issue") or {}).get("id") == node_ids[0] for index in range(len(children))):
        raise PdlcError("GitHub returned an incomplete sub-issue link mutation")


def link_subissues(parent: int | str, children: list[int | str]) -> None:
    pending = [str(child) for child in children]
    last_error: PdlcError | None = None

    for _ in range(2):
        try:
            _link_subissues_once(parent, pending)
        except PdlcError as error:
            last_error = error

        linked = {str(task["number"]) for task in subissues_for(str(parent))}
        pending = [child for child in pending if child not in linked]
        if not pending:
            return

    detail = f"; last error: {last_error}" if last_error else ""
    raise PdlcError(f"created task Issues remain unlinked: {','.join(pending)}{detail}")


# Delivery task sub-issues of a parent, as a list of
# {number, title, url, state, body, comments, taskId}. taskId is the stable
# WORK-NNN-TASK-NNN prefix parsed off the title, or None for a sub-issue
# that has none; comments is the list of comment body strings, from which the
# task's plan and implementation progress are derived.
def subissues_for(issue: str) -> list[dict]:
    if not issue.isdigit():
        raise PdlcError(f"Issue number must be numeric: {issue}")

    owner, repository = owner_repository()

    fixture = os.environ.get("PDLC_SUBISSUES_FILE")
    if fixture:
        with open(fixture) as handle:
            nodes = json.load(handle)
        return [{**node, "comments": comment_bodies(node.get("comments"))} for node in nodes]

    data = run_graphql(SUBISSUES_QUERY, owner=owner, repo=repository, number=int(issue))
    nodes = data["data"]["repository"]["issue"]["subIssues"]["nodes"]

    result = []
    for node in nodes:
        match = TASK_ID_PATTERN.match(node["title"])
        result.append({
            **node,
            "comments": comment_bodies(node.get("comments")),
            "taskId": match.group(1) if match else None,
        })
    return result


# Creates or updates one delivery task, matched by its stable
# WORK-NNN-TASK-NNN identity rather than its wording, so a reworded task is
# still the same task. Returns {action, taskId, number, title, url}.
def _upsert_task(
    parent: str,
    task_id: str,
    title: str,
    body_path: str,
    match: dict | None,
    *,
    body_text: str | None = None,
    link_created: bool = True,
) -> dict:
    full_title = f"WORK-{parent}-{task_id} {title}"
    body_text = body_text if body_text is not None else Path(body_path).read_text()

    if match:
        number = match["number"]
        title_changed = match["title"] != full_title
        # Compare against the neutralized form, since that is what a prior run
        # wrote — otherwise a task carrying a `#123` would re-edit every pass.
        body_changed = (match.get("body") or "") != neutralize_refs(body_text)
        if title_changed or body_changed:
            with body_file(body_text) as path:
                run_gh(["issue", "edit", str(number), *repo_args(), "--title", full_title, "--body-file", path])
            action = "retitled" if title_changed else "updated"
        else:
            action = "unchanged"
        url = match["url"]
    else:
        with body_file(body_text) as path:
            output = run_gh(["issue", "create", *repo_args(), "--title", full_title, "--body-file", path])
        url = output.strip().splitlines()[-1]
        number_text = url.rsplit("/", 1)[-1]
        if not number_text.isdigit():
            raise PdlcError(f"could not parse Issue number from: {url}")
        number = int(number_text)
        if link_created:
            link_subissue(parent, number)
        action = "created"

    return {"action": action, "taskId": task_id, "number": number, "title": full_title, "url": url}


def _recover_unlinked_tasks(parent: str, task_ids: list[str], existing: list[dict]) -> list[dict]:
    if os.environ.get("PDLC_ITEMS_FILE"):
        return []
    existing_ids = {task.get("taskId") for task in existing}
    missing_ids = set(task_ids) - existing_ids
    if not missing_ids:
        return []

    candidates = run_gh_json([
        "issue", "list", *repo_args(), "--state", "all",
        "--search", f"in:title WORK-{parent}-TASK-",
        "--limit", "100", "--json", "number,title,url,state,body",
    ])
    recovered: dict[str, dict] = {}
    for candidate in candidates:
        match = TASK_TITLE_PATTERN.match(candidate.get("title") or "")
        if not match or match.group(1) != parent or match.group(2) not in missing_ids:
            continue
        task_id = match.group(2)
        if task_id in recovered:
            raise PdlcError(f"multiple unlinked Issues carry stable identity WORK-{parent}-{task_id}")
        recovered[task_id] = {**candidate, "taskId": task_id}
    return list(recovered.values())


def upsert_tasks(parent: str, tasks: list[dict], existing: list[dict]) -> list[dict]:
    recovered = _recover_unlinked_tasks(parent, [task["id"] for task in tasks], existing)
    existing_by_id = {task["taskId"]: task for task in [*existing, *recovered] if task.get("taskId")}
    numbers_to_link = [task["number"] for task in recovered]
    results = []
    try:
        for task in tasks:
            result = _upsert_task(
                parent,
                task["id"],
                task["title"],
                task["body"],
                existing_by_id.get(task["id"]),
                body_text=task.get("bodyText"),
                link_created=False,
            )
            results.append(result)
            if result["action"] == "created":
                numbers_to_link.append(result["number"])
    except Exception:
        link_subissues(parent, numbers_to_link)
        raise

    link_subissues(parent, numbers_to_link)
    return results


def tasks_by_number(numbers: list[str]) -> list[dict]:
    for number in numbers:
        if not number.isdigit():
            raise PdlcError(f"Issue number must be numeric: {number}")

    owner, repository = owner_repository()
    selections = "\n".join(
        f"issue{index}: issue(number: {int(number)}) {{ number title url state body "
        f"comments(first: 100) {{ nodes {{ body }} }} }}"
        for index, number in enumerate(numbers)
    )
    query = f"""
    query($owner: String!, $repo: String!) {{
      repository(owner: $owner, name: $repo) {{
        {selections}
      }}
    }}
    """
    data = run_graphql(query, owner=owner, repo=repository)["data"]["repository"]
    tasks = [data[f"issue{index}"] for index in range(len(numbers))]
    if any(task is None for task in tasks):
        raise PdlcError("one or more delivery task Issues do not exist")

    result = []
    for task in tasks:
        match = TASK_ID_PATTERN.match(task["title"])
        result.append({
            **task,
            "comments": comment_bodies(task.get("comments")),
            "taskId": match.group(1) if match else None,
        })
    return result


# Issue evidence

# Posts an Issue comment from a literal string, an existing file's contents,
# or `-` for stdin. With a marker, it opens with a PDLC-<MARKER> stamp so
# orientation can tell a durable PDLC record from ordinary Issue chatter —
# require_marker validates the vocabulary (see pdlc_common.py) and a body
# that already starts with one is refused. Without a marker it posts as-is,
# for ad-hoc comments that aren't PDLC evidence.
def post_comment(issue: str, text_or_file: str, marker: str | None = None) -> str:
    content_text = compose_comment(marker, read_body_source(text_or_file, label="evidence"))
    with body_file(content_text) as body_path:
        return run_gh(["issue", "comment", str(issue), *repo_args(), "--body-file", body_path])


def comments_for_issue(issue: str) -> list[dict]:
    if not issue.isdigit():
        raise PdlcError(f"Issue number must be numeric: {issue}")
    if os.environ.get("PDLC_ITEMS_FILE"):
        comments = item_for_issue(issue).get("comments") or []
        return [
            comment if isinstance(comment, dict) else {
                "body": comment,
                "createdAt": "1970-01-01T00:00:00Z",
                "url": "",
                "author": {"login": "fixture"},
            }
            for comment in comments
        ]
    owner, repository = owner_repository()
    pages = run_gh_json([
        "api", "--paginate", "--slurp",
        f"repos/{owner}/{repository}/issues/{issue}/comments",
    ])
    return [
        {
            "body": comment["body"],
            "createdAt": comment["created_at"],
            "url": comment["html_url"],
            "author": {"login": (comment.get("user") or {}).get("login")},
        }
        for page in pages
        for comment in page
    ]
