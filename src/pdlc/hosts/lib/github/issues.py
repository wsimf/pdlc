"""GitHub Issues transport for the GitHub work-item backend: delivery
sub-issues (read, upsert, link) and evidence comments. Pull requests belong
to `code_host`; body section editing and evidence parsing are pure and live
in `pdlc.domain.model`. Everything here is reached only through
`workitem_backend.py`.
"""

from __future__ import annotations

import contextlib
import re

from pdlc.hosts.lib.github.transport import (
    assignee_args,
    body_file,
    neutralize_refs,
    restore_refs,
    owner_repository,
    repo_args,
    run_gh,
    run_gh_json,
    run_graphql,
)
import pdlc.hosts.lib.github.pr_registry as pr_registry
from pdlc.domain.lifecycle import PdlcError, TransientError
from pdlc.domain.model import (
    TASK_ID_PATTERN,
    TASK_TITLE_PATTERN,
    comment_bodies,
    comment_objects,
)

# Shared comment sub-selection for the task GraphQL queries. Carries enough per
# comment (author, timestamp, url) to render a task's own `## User Comments`
# section, not just derive its plan/implementation progress from the bodies.
TASK_COMMENTS_SELECTION = (
    "comments(last: 100) { nodes { body createdAt url author { login } } "
    "totalCount pageInfo { hasPreviousPage startCursor } }"
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
          __TASK_COMMENTS__
        }
      }
    }
  }
}
""".replace("__TASK_COMMENTS__", TASK_COMMENTS_SELECTION)


def link_subissue(parent: int | str, child: int | str) -> None:
    link_subissues(parent, [child])


def remove_subissue(parent: int | str, child: int | str) -> None:
    """Close and detach a descoped task while retaining its Issue history."""
    if not str(parent).isdigit() or not str(child).isdigit():
        raise PdlcError("sub-issue numbers must be numeric")
    owner, repository = owner_repository()
    query = f"""
    query($owner: String!, $repo: String!) {{
      repository(owner: $owner, name: $repo) {{
        parent: issue(number: {int(parent)}) {{ id }}
        child: issue(number: {int(child)}) {{ id state }}
      }}
    }}
    """
    issues = run_graphql(query, owner=owner, repo=repository)["data"]["repository"]
    parent_id = (issues.get("parent") or {}).get("id")
    child_id = (issues.get("child") or {}).get("id")
    if not parent_id or not child_id:
        raise PdlcError("one or more sub-issue nodes do not exist")
    if issues["child"].get("state") != "CLOSED":
        run_gh(["issue", "close", str(child), *repo_args()])
    mutation = """mutation($parentId: ID!, $childId: ID!) {
      removeSubIssue(input: {issueId: $parentId, subIssueId: $childId}) { issue { id } }
    }"""
    result = run_graphql(mutation, parentId=parent_id, childId=child_id)
    if (((result.get("data") or {}).get("removeSubIssue") or {}).get("issue") or {}).get("id") != parent_id:
        raise PdlcError("GitHub returned an incomplete sub-issue removal")


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
    message = f"created task Issues remain unlinked: {','.join(pending)}{detail}"
    if isinstance(last_error, TransientError):
        raise TransientError(message, attempts=last_error.attempts)
    raise PdlcError(message)


# A task Issue in the form pdlc wrote it: the registry block split out into
# `prs` and loose `#123` escapes restored.
def _readable(node: dict) -> dict:
    view = pr_registry.view(node)
    return {**view, "body": restore_refs(view["body"])}


# A GraphQL comment payload with every body restored, keeping its paging shape.
def _restored_comments(raw: object) -> object:
    def restored(comment: object) -> object:
        if isinstance(comment, dict):
            return {**comment, "body": restore_refs(comment.get("body") or "")}
        return restore_refs(str(comment))
    if isinstance(raw, dict):
        return {**raw, "nodes": [restored(comment) for comment in raw.get("nodes") or []]}
    if isinstance(raw, list):
        return [restored(comment) for comment in raw]
    return raw


# Delivery task sub-issues of a parent, as a list of
# {number, title, url, state, body, comments, taskId, prs}. taskId is the stable
# WORK-NNN-TASK-NNN prefix parsed off the title, or None for a sub-issue
# that has none; comments is the list of comment body strings, from which the
# task's plan and implementation progress are derived. `body` is the human
# content only — the registry block is split out into `prs`.
def subissues_for(issue: str, *, include_comments: bool = True) -> list[dict]:
    if not issue.isdigit():
        raise PdlcError(f"Issue number must be numeric: {issue}")

    owner, repository = owner_repository()

    query = SUBISSUES_QUERY
    if not include_comments:
        query = query.replace(TASK_COMMENTS_SELECTION, "")
    data = run_graphql(query, owner=owner, repo=repository, number=int(issue))
    nodes = data["data"]["repository"]["issue"]["subIssues"]["nodes"]

    result = []
    for node in nodes:
        match = TASK_ID_PATTERN.match(node["title"])
        comments = _restored_comments(node.get("comments"))
        result.append(_readable({
            **node,
            "comments": comment_bodies(comments),
            "commentObjects": comment_objects(comments),
            "commentsMeta": _comments_metadata(comments),
            "taskId": match.group(1) if match else None,
        }))
    return result


# Creates or updates one delivery task, matched by its stable
# WORK-NNN-TASK-NNN identity rather than its wording, so a reworded task is
# still the same task. Returns {action, taskId, number, title, url}.
def _upsert_task(
    parent: str,
    task_id: str,
    title: str,
    body_text: str,
    match: dict | None,
    *,
    link_created: bool = True,
) -> dict:
    full_title = f"WORK-{parent}-{task_id} {title}"

    if match:
        number = match["number"]
        title_changed = match["title"] != full_title
        # Compare the forms GitHub would store, so a body differing only in how
        # a `#123` is escaped is not re-edited every pass. `match` already has
        # its registry block split out, so the attached pull requests are
        # re-attached to the rewrite rather than counted as a change.
        stored = match.get("body") or ""
        body_changed = neutralize_refs(stored) != neutralize_refs(body_text)
        if title_changed or body_changed:
            with body_file(pr_registry.attach(body_text, match.get("prs"))) as path:
                run_gh(["issue", "edit", str(number), *repo_args(), "--title", full_title, "--body-file", path])
            action = "retitled" if title_changed else "updated"
        else:
            action = "unchanged"
        url = match["url"]
    else:
        with body_file(body_text) as path:
            output = run_gh(["issue", "create", *repo_args(), "--title", full_title, "--body-file", path, *assignee_args()])
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
        # Recovered candidates carry raw Issue bodies; normalize them to the
        # same shape as `existing` so the upsert compare sees one form.
        recovered[task_id] = _readable({**candidate, "taskId": task_id})
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
                task["bodyText"],
                existing_by_id.get(task["id"]),
                link_created=False,
            )
            results.append(result)
            if result["action"] == "created":
                numbers_to_link.append(result["number"])
    except Exception:
        # Link what was created, but report the failure that stopped the loop.
        with contextlib.suppress(PdlcError):
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
        + TASK_COMMENTS_SELECTION + " }"
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
        comments = _restored_comments(task.get("comments"))
        result.append(_readable({
            **task,
            "comments": comment_bodies(comments),
            "commentObjects": comment_objects(comments),
            "commentsMeta": _comments_metadata(comments),
            "taskId": match.group(1) if match else None,
        }))
    return result


# Issue evidence

def post_comment(issue: str, body: str) -> str:
    with body_file(body) as body_path:
        return run_gh(["issue", "comment", str(issue), *repo_args(), "--body-file", body_path])


_COMMENT_ID_PATTERN = re.compile(r"#issuecomment-(\d+)$")


def edit_comment(comment_url: str, body: str) -> str:
    """Replace an existing issue comment's body in place, addressed by the
    `html_url` `post_comment`/`comments_for_issue` returned for it."""
    match = _COMMENT_ID_PATTERN.search(comment_url)
    if not match:
        raise PdlcError(f"cannot parse a GitHub comment id from: {comment_url}")
    owner, repository = owner_repository()
    with body_file(body) as body_path:
        # `-f` (`--raw-field`) takes `@path` as a literal string; only `-F`
        # (`--field`) reads the file it names.
        run_gh([
            "api", "--method", "PATCH",
            f"repos/{owner}/{repository}/issues/comments/{match.group(1)}",
            "-F", f"body=@{body_path}",
        ])
    return comment_url


def delete_comment(comment_url: str) -> None:
    """Permanently remove an existing issue comment, addressed by the same
    `html_url` reference `edit_comment` accepts. Used when invalidation
    should retire stale task evidence outright rather than leave a
    superseded body on record."""
    match = _COMMENT_ID_PATTERN.search(comment_url)
    if not match:
        raise PdlcError(f"cannot parse a GitHub comment id from: {comment_url}")
    owner, repository = owner_repository()
    try:
        run_gh(["api", "--method", "DELETE", f"repos/{owner}/{repository}/issues/comments/{match.group(1)}"])
    except TransientError:
        raise
    except PdlcError as error:
        # Already gone, e.g. a retried delete whose first attempt landed.
        if "Not Found" not in str(error) and "HTTP 404" not in str(error):
            raise


def comments_for_issue(issue: str) -> list[dict]:
    if not issue.isdigit():
        raise PdlcError(f"Issue number must be numeric: {issue}")
    owner, repository = owner_repository()
    pages = run_gh_json([
        "api", "--paginate", "--slurp",
        f"repos/{owner}/{repository}/issues/{issue}/comments",
    ])
    return [
        {
            "body": restore_refs(comment["body"] or ""),
            "createdAt": comment["created_at"],
            "url": comment["html_url"],
            "author": {"login": (comment.get("user") or {}).get("login")},
        }
        for page in pages
        for comment in page
    ]


def comments_page(issue: str, page: int = 1, per_page: int = 100):
    from pdlc.hosts.workitem_host.base import CommentPage
    if not issue.isdigit() or page < 1 or per_page != 100:
        raise PdlcError("comments page must be >= 1 and use 100 comments per page")
    owner, repository = owner_repository()
    count_query = "query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){issue(number:$number){comments(last:100){totalCount pageInfo{hasPreviousPage startCursor}}}}}"
    total = run_graphql(count_query, owner=owner, repo=repository, number=int(issue))["data"]["repository"]["issue"]["comments"]["totalCount"]
    total_pages = max(1, (total + per_page - 1) // per_page)
    newest_page = total_pages - page + 1
    if newest_page < 1:
        return CommentPage([], page, per_page, total, False)
    oldest_page = max(1, newest_page - 1)
    raw_pages = []
    for api_page in range(oldest_page, newest_page + 1):
        raw_pages.append(run_gh_json(["api", "--method", "GET", f"repos/{owner}/{repository}/issues/{issue}/comments", "-f", f"per_page={per_page}", "-f", f"page={api_page}"]))
    raw = [comment for batch in raw_pages for comment in batch]
    comments = [{"body": restore_refs(c["body"] or ""), "createdAt": c["created_at"], "url": c["html_url"], "author": {"login": (c.get("user") or {}).get("login")}} for c in reversed(raw)]
    offset = max(0, len(raw) - (total - (page - 1) * per_page))
    comments = comments[offset:offset + per_page]
    return CommentPage(comments, page, per_page, total, total > page * per_page)


def _comments_metadata(raw: object) -> dict:
    if not isinstance(raw, dict):
        return {"totalCount": len(raw) if isinstance(raw, list) else 0, "pageInfo": {}}
    nodes = raw.get("nodes") or []
    return {"totalCount": raw.get("totalCount", len(nodes)), "pageInfo": raw.get("pageInfo") or {}}
