"""GitHub work-item backend: the PDLC record is a GitHub Issue, its state is a
GitHub Project (v2) item, and its delivery tasks are sub-issues.

Most operations delegate to the established project / issues
helpers; this class only gives them the WorkItemBackend shape and owns the
raw body write and record creation.
"""

from __future__ import annotations

from pdlc.domain.records import Comment, CreatedRecord, QueueItemSummary, Task, TaskInput, TaskPublication, WorkItem

import pdlc.hosts.lib.github.issues as github_issues
import pdlc.hosts.lib.github.pr_registry as pr_registry
import pdlc.hosts.lib.github.project as github_project
from pdlc.hosts.lib.github.transport import (
    assignee_args,
    body_file,
    repo_args,
    run_gh,
    run_gh_json,
)
from pdlc.config import get_config
from pdlc.domain.lifecycle import PdlcError, TransientError
from pdlc.domain.workflow import WorkType
from pdlc.hosts.workitem_host.base import CommentPage, WorkItemBackend


class GitHubWorkItemBackend(WorkItemBackend):
    capabilities = {"subissue_graph", "queue_scan"}

    # --- resolution ---

    def resolve(self, ref: str) -> WorkItem:
        item = github_project.item_for_issue(ref if ref.isdigit() else github_project.issue_for_slug(ref))
        body = item.get("issueBody") or ""
        return {**item, "issueBody": pr_registry.strip(body), "prs": pr_registry.prs(body)}

    def queue_items(self) -> list[QueueItemSummary]:
        return github_project.queue_items()

    # --- state fields ---

    def set_state(self, item_id: str, status: str, gate: str, lifecycle: str) -> None:
        github_project.set_state(item_id, status, gate, lifecycle)

    def set_gate(self, item_id: str, gate: str) -> None:
        github_project.edit_single_select(item_id, "Gate State", gate)

    def set_slug(self, item_id: str, value: str) -> None:
        github_project.set_slug(item_id, value)

    def set_skipped_states(self, item_id: str, value: str) -> None:
        github_project.set_skipped_states(item_id, value)

    def close_record(self, ref: str) -> None:
        run_gh(["issue", "close", str(ref), *repo_args()])

    # --- body ---

    def _raw_body(self, ref: str) -> str:
        """The Issue body as GitHub stores it, registry block included."""
        return run_gh_json(["issue", "view", str(ref), *repo_args(), "--json", "body"]).get("body") or ""

    def write_body(self, ref: str, body: str) -> None:
        # `body` is human content: callers never see the registry block, so it
        # is re-read and re-attached here rather than trusted to survive a
        # caller's round trip.
        with body_file(pr_registry.restore(self._raw_body(ref), body)) as path:
            run_gh(["issue", "edit", str(ref), *repo_args(), "--body-file", path])

    # --- comments ---

    def comments(self, ref: str) -> list[Comment]:
        return github_issues.comments_for_issue(ref)

    def comments_page(self, ref: str, page: int = 1, per_page: int = 100) -> CommentPage:
        return github_issues.comments_page(ref, page, per_page)

    def post_comment(self, ref: str, body: str) -> str:
        return github_issues.post_comment(str(ref), body)

    def edit_comment(self, ref: str, comment_ref: str, body: str) -> str:
        return github_issues.edit_comment(comment_ref, body)

    def delete_comment(self, ref: str, comment_ref: str) -> None:
        github_issues.delete_comment(comment_ref)

    def post_blocker(self, ref: str, body: str) -> str:
        # No dedicated blocker surface on GitHub yet — the PDLC-DECISION marker
        # and the Decision Required gate carry the signal. Revisit with a pinned
        # comment or a label once that is worth the extra API calls.
        return github_issues.post_comment(str(ref), body)

    # --- delivery tasks ---

    def tasks(self, ref: str) -> list[Task]:
        return github_issues.subissues_for(ref)

    def tasks_by_number(self, numbers: list[str]) -> list[Task]:
        return github_issues.tasks_by_number(numbers)

    def upsert_tasks(self, parent: str, tasks: list[TaskInput], existing: list[Task]) -> list[TaskPublication]:
        return github_issues.upsert_tasks(parent, tasks, existing)

    def close_task(self, task_ref: str) -> None:
        run_gh(["issue", "close", str(task_ref), *repo_args()])

    def remove_task(self, parent: str, task_ref: str) -> None:
        github_issues.remove_subissue(parent, task_ref)

    def reopen_task(self, task_ref: str) -> None:
        run_gh(["issue", "reopen", str(task_ref), *repo_args()])

    def task_pr_numbers(self, ref: str) -> list[int]:
        return sorted({number for task in github_issues.subissues_for(ref, include_comments=False) for number in task["prs"]})

    # --- attached pull requests ---

    # Records and delivery tasks are both Issues, so one implementation serves
    # each: the registry lives in the Issue body either way.

    def attach_pr(self, ref: str, pr_number: int) -> list[int]:
        stored = self._raw_body(ref)
        updated, numbers = pr_registry.with_pr(stored, int(pr_number))
        if updated != stored:
            with body_file(updated) as path:
                run_gh(["issue", "edit", str(ref), *repo_args(), "--body-file", path])
        return numbers

    def attached_prs(self, ref: str) -> list[int]:
        return pr_registry.prs(self._raw_body(ref))

    # --- creation ---

    def create(self, title: str, body: str, slug: str, work_type: WorkType = WorkType.FEATURE) -> CreatedRecord:
        work_type = self._validated_work_type(work_type)
        if work_type is not WorkType.FEATURE:
            raise PdlcError(f"GitHub creation is unavailable for work type: {work_type.value}")
        config = get_config()
        with body_file(body) as body_path:
            # `gh issue create` has no --json: the new Issue's URL is the last
            # line of its output.
            output = run_gh([
                "issue", "create", *repo_args(), "--title", title,
                "--body-file", body_path, *assignee_args(),
            ])

        url = output.strip().splitlines()[-1]
        number = url.rsplit("/", 1)[-1]
        if not number.isdigit():
            raise PdlcError(f"could not parse Issue number from: {url}")

        try:
            item = run_gh_json([
                "project", "item-add", config.project_number,
                "--owner", config.project_owner, "--url", url, "--format", "json",
            ])
        except TransientError as error:
            # Name the Issue that now exists, so recovery finishes it rather
            # than creating a second one.
            raise TransientError(f"{error}; created {url}, but it may not be on the project yet", attempts=error.attempts) from error
        return {"id": item["id"], "number": int(number), "url": url}

    # --- identity ---

    def current_actor(self) -> str:
        return run_gh_json(["api", "user"])["login"]

    def ref_label(self) -> str:
        repository = get_config().repository
        return repository.rsplit("/", 1)[-1] if repository else "pdlc"
