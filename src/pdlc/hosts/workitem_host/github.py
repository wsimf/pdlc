"""GitHub work-item backend: the PDLC record is a GitHub Issue, its state is a
GitHub Project (v2) item, and its delivery tasks are sub-issues.

Most operations delegate to the established github_project / github_issues
helpers; this class only gives them the WorkItemBackend shape and owns the
raw body write and record creation.
"""

from __future__ import annotations

import pdlc.hosts.github_issues as github_issues
import pdlc.hosts.github_project as github_project
from pdlc.hosts.github_common import (
    body_file,
    repo_args,
    run_gh,
    run_gh_json,
)
from pdlc.config import get_config
from pdlc.domain.lifecycle import PdlcError
from pdlc.hosts.workitem_host.base import WorkItemBackend


class GitHubWorkItemBackend(WorkItemBackend):
    capabilities = {"subissue_graph", "queue_scan"}

    # --- resolution ---

    def resolve(self, ref: str) -> dict:
        return github_project.item_for_issue(ref)

    def all_items(self) -> dict:
        return github_project.project_items()

    # --- state fields ---

    def set_state(self, item_id: str, status: str, gate: str, lifecycle: str) -> None:
        github_project.set_state(item_id, status, gate, lifecycle)

    def set_gate(self, item_id: str, gate: str) -> None:
        github_project.edit_single_select(item_id, "Gate State", gate)

    def set_slug(self, item_id: str, value: str) -> None:
        github_project.set_slug(item_id, value)

    def set_skipped_states(self, item_id: str, value: str) -> None:
        github_project.set_skipped_states(item_id, value)

    # --- body ---

    def write_body(self, ref: str, body: str) -> None:
        with body_file(body) as path:
            run_gh(["issue", "edit", str(ref), *repo_args(), "--body-file", path])

    # --- comments ---

    def comments(self, ref: str) -> list[dict]:
        return github_issues.comments_for_issue(ref)

    def post_comment(self, ref: str, body: str) -> str:
        return github_issues.post_comment(str(ref), body, None)

    def post_blocker(self, ref: str, body: str) -> str:
        # No dedicated blocker surface on GitHub yet — the PDLC-DECISION marker
        # and the Decision Required gate carry the signal. Revisit with a pinned
        # comment or a label once that is worth the extra API calls.
        return github_issues.post_comment(str(ref), body, None)

    # --- delivery tasks ---

    def tasks(self, ref: str) -> list[dict]:
        return github_issues.subissues_for(ref)

    def tasks_by_number(self, numbers: list[str]) -> list[dict]:
        return github_issues.tasks_by_number(numbers)

    def upsert_tasks(self, parent: str, tasks: list[dict], existing: list[dict]) -> list[dict]:
        return github_issues.upsert_tasks(parent, tasks, existing)

    def write_task_body(self, task_ref: str, body: str) -> None:
        with body_file(body) as path:
            run_gh(["issue", "edit", str(task_ref), *repo_args(), "--body-file", path])

    def close_task(self, task_ref: str) -> None:
        run_gh(["issue", "close", str(task_ref), *repo_args()])

    # --- creation ---

    def create(self, title: str, body: str, slug: str) -> dict:
        config = get_config()
        with body_file(body) as body_path:
            # `gh issue create` has no --json: the new Issue's URL is the last
            # line of its output.
            output = run_gh(["issue", "create", *repo_args(), "--title", title, "--body-file", body_path])

        url = output.strip().splitlines()[-1]
        number = url.rsplit("/", 1)[-1]
        if not number.isdigit():
            raise PdlcError(f"could not parse Issue number from: {url}")

        item = run_gh_json([
            "project", "item-add", config.project_number,
            "--owner", config.project_owner, "--url", url, "--format", "json",
        ])
        return {"id": item["id"], "number": int(number), "url": url}

    # --- identity ---

    def current_actor(self) -> str:
        return run_gh_json(["api", "user"])["login"]

    def ref_label(self) -> str:
        repository = get_config().repository
        return repository.rsplit("/", 1)[-1] if repository else "pdlc"
