"""Opt-in end-to-end coverage against the real GitHub Project host.

Run explicitly with ``PDLC_LIVE_E2E=1``. The test uses the dedicated
``wsimf/pdlc`` repository and ``pdlc-scratch`` Project, creates its own Issue
and sub-issue, and closes all created Issues during cleanup.
"""

from __future__ import annotations

import os
import time
import unittest
from uuid import uuid4

from pdlc.config import reset_config
from pdlc.hosts.lib.github.transport import run_gh, run_gh_json
from pdlc.hosts.lib.github.workitem_backend import GitHubWorkItemBackend
from pdlc.hosts.workitem_host import reset_backend


REPOSITORY = "wsimf/pdlc"
PROJECT_OWNER = "wsimf"
PROJECT_NUMBER = "4"


@unittest.skipUnless(os.environ.get("PDLC_LIVE_E2E") == "1", "set PDLC_LIVE_E2E=1 to run live GitHub tests")
class GitHubLiveEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = {
            key: os.environ.get(key)
            for key in (
                "PDLC_BACKEND", "PDLC_CODE_HOST", "PDLC_REPOSITORY",
                "PDLC_PROJECT_OWNER", "PDLC_PROJECT_NUMBER",
            )
        }
        os.environ.update({
            "PDLC_BACKEND": "github",
            "PDLC_CODE_HOST": "github",
            "PDLC_REPOSITORY": REPOSITORY,
            "PDLC_PROJECT_OWNER": PROJECT_OWNER,
            "PDLC_PROJECT_NUMBER": PROJECT_NUMBER,
        })
        reset_config()
        reset_backend()
        self.backend = GitHubWorkItemBackend()
        self.parent_number: int | None = None
        self.parent_item_id: str | None = None
        self.task_number: int | None = None
        self.addCleanup(self._cleanup_remote)
        self.addCleanup(self._restore_environment)

    def _restore_environment(self) -> None:
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_config()
        reset_backend()

    def _cleanup_remote(self) -> None:
        if self.task_number is not None:
            run_gh(["issue", "close", str(self.task_number), "--repo", REPOSITORY, "--reason", "not planned"])
        if self.parent_number is not None:
            run_gh(["issue", "close", str(self.parent_number), "--repo", REPOSITORY, "--reason", "not planned"])
        created_numbers = {number for number in (self.parent_number, self.task_number) if number is not None}
        if created_numbers:
            project = run_gh_json([
                "project", "item-list", PROJECT_NUMBER, "--owner", PROJECT_OWNER,
                "--format", "json", "--limit", "100",
            ])
            for item in project.get("items", []):
                content = item.get("content") or {}
                if content.get("number") not in created_numbers:
                    continue
                run_gh([
                    "project", "item-delete", PROJECT_NUMBER, "--owner", PROJECT_OWNER,
                    "--id", item["id"],
                ])

    def test_real_project_record_and_task_lifecycle(self) -> None:
        marker = uuid4().hex[:12]
        slug = f"live-e2e-{marker}"
        title = f"[LIVE E2E] GitHub host {marker}"
        body = f"## Product\n\nLive GitHub host probe `{marker}`.\n"

        created = self.backend.create(title, body, slug)
        self.parent_number = created["number"]
        self.parent_item_id = created["id"]

        item = self.backend.resolve(str(self.parent_number))
        self.assertEqual(item["content"]["title"], title)
        self.assertEqual(item["issueBody"], body)
        self.assertEqual(item["Slug"], "")

        assert self.parent_item_id is not None
        self.backend.set_state(self.parent_item_id, "Product", "Pending", "Planning")
        self.backend.set_slug(self.parent_item_id, slug)
        self.backend.set_skipped_states(self.parent_item_id, "UI")
        rewritten_body = f"## Product\n\nUpdated live probe `{marker}`.\n"
        self.backend.write_body(str(self.parent_number), rewritten_body)
        comment_body = f"LIVE-E2E comment {marker}"
        comment_ref = self.backend.post_comment(str(self.parent_number), comment_body)

        resolved = self.backend.resolve(slug)
        self.assertEqual(resolved["issueBody"], rewritten_body)
        self.assertEqual(resolved["Slug"], slug)
        self.assertEqual(resolved["Skipped States"], "UI")
        self.assertEqual(resolved["Status"], "Product")
        self.assertEqual(resolved["Gate State"], "Pending")
        self.assertEqual(resolved["Lifecycle"], "Planning")
        self.assertTrue(comment_ref)
        self.assertTrue(any(comment["body"] == comment_body for comment in self.backend.comments(str(self.parent_number))))

        task_input = [{
            "id": "TASK-001",
            "title": "[CORE] live task",
            "bodyText": f"Acceptance probe `{marker}`.\n",
        }]
        first = self.backend.upsert_tasks(str(self.parent_number), task_input, [])
        self.assertEqual(first[0]["action"], "created")
        self.task_number = first[0]["number"]
        tasks = self.backend.tasks(str(self.parent_number))
        self.assertEqual(tasks[0]["taskId"], "TASK-001")
        self.assertEqual(tasks[0]["body"], task_input[0]["bodyText"])

        second = self.backend.upsert_tasks(str(self.parent_number), task_input, tasks)
        self.assertEqual(second[0]["action"], "unchanged")

        self.backend.close_task(str(self.task_number))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            task = self.backend.tasks_by_number([str(self.task_number)])[0]
            if task["state"] == "CLOSED":
                break
            time.sleep(1)
        self.assertEqual(task["state"], "CLOSED")
