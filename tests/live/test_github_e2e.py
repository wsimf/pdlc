"""Opt-in end-to-end coverage against the real GitHub Project host.

Exercises every `WorkItemBackend` method against the exact `gh` commands
`GitHubWorkItemBackend` issues, down to their arguments — not the compiled
Python surface, since that would not catch a wrong flag or field name reaching
the real API. Skips unless `tests/live/live_config.toml` carries a `[github]`
table naming a dedicated scratch repository and Project; see
`live_config.toml.example`. Creates its own Issues and closes/unboards every
one it created during cleanup, and sweeps any `[LIVE E2E]` issues a prior run
left behind (e.g. a crash before its own cleanup ran) before creating its own.
"""

from __future__ import annotations

import time
import unittest
from uuid import uuid4

from pdlc.config import Config, install_config, reset_config
from pdlc.domain.records import TaskInput
from pdlc.hosts.lib.github.transport import run_gh, run_gh_json
from pdlc.hosts.lib.github.workitem_backend import GitHubWorkItemBackend
from pdlc.hosts.workitem_host import reset_backend
from tests.live._config import CONFIG_PATH, load_section

_GITHUB = load_section("github")


@unittest.skipUnless(
    _GITHUB is not None,
    f"add a [github] table to {CONFIG_PATH} to run live GitHub tests",
)
class GitHubLiveEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        assert _GITHUB is not None
        self.repository = _GITHUB["repository"]
        self.project_owner = _GITHUB["project_owner"]
        self.project_number = _GITHUB["project_number"]

        install_config(Config(
            backend="github",
            code_host="github",
            repository=self.repository,
            project_owner=self.project_owner,
            project_number=self.project_number,
        ))
        reset_backend()
        self._sweep_orphaned_live_issues()
        self.backend = GitHubWorkItemBackend()
        self.parent_number: int | None = None
        self.task_number: int | None = None
        # Cleanups run last-registered-first; register the remote cleanup last
        # so it still runs before config/backend are reset.
        self.addCleanup(reset_backend)
        self.addCleanup(reset_config)
        self.addCleanup(self._cleanup_remote)

    def _sweep_orphaned_live_issues(self) -> None:
        """Close and unboard every open `[LIVE E2E]` issue already in the
        repository, left behind by a run that crashed before its own
        `_cleanup_remote` ran. Runs before this test creates its own issue, so
        debris never accumulates across runs even when one of them fails."""
        stale = run_gh_json([
            "issue", "list", "--repo", self.repository, "--state", "open",
            "--search", "[LIVE E2E] in:title", "--json", "number", "--limit", "100",
        ])
        self._close_and_unboard({item["number"] for item in stale})

    def _cleanup_remote(self) -> None:
        self._close_and_unboard({
            number for number in (self.parent_number, self.task_number) if number is not None
        })

    def _close_and_unboard(self, numbers: set[int]) -> None:
        if not numbers:
            return
        for number in numbers:
            run_gh(["issue", "close", str(number), "--repo", self.repository, "--reason", "not planned"])
        project = run_gh_json([
            "project", "item-list", self.project_number, "--owner", self.project_owner,
            "--format", "json", "--limit", "100",
        ])
        for item in project.get("items", []):
            content = item.get("content") or {}
            if content.get("number") not in numbers:
                continue
            run_gh([
                "project", "item-delete", self.project_number, "--owner", self.project_owner,
                "--id", item["id"],
            ])

    def test_real_project_record_and_task_lifecycle(self) -> None:
        marker = uuid4().hex[:12]
        slug = f"live-e2e-{marker}"
        title = f"[LIVE E2E] GitHub host {marker}"
        body = f"## Product\n\nLive GitHub host probe `{marker}`.\n"

        # --- create / resolve ---
        created = self.backend.create(title, body, slug)
        self.parent_number = created["number"]
        parent_item_id = created["id"]

        item = self.backend.resolve(str(self.parent_number))
        self.assertEqual(item["content"]["title"], title)
        self.assertEqual(item["issueBody"], body)
        self.assertEqual(item["Slug"], "")

        # --- state fields ---
        self.backend.set_state(parent_item_id, "Product", "Pending", "Planning")
        self.backend.set_gate(parent_item_id, "Review Required")
        self.backend.set_slug(parent_item_id, slug)
        self.backend.set_skipped_states(parent_item_id, "UI")

        # --- body ---
        rewritten_body = f"## Product\n\nUpdated live probe `{marker}`.\n"
        self.backend.write_body(str(self.parent_number), rewritten_body)

        # --- comments ---
        comment_body = f"LIVE-E2E comment {marker}"
        comment_ref = self.backend.post_comment(str(self.parent_number), comment_body)
        edited_body = f"LIVE-E2E comment {marker} (edited)"
        self.backend.edit_comment(str(self.parent_number), comment_ref, edited_body)
        blocker_ref = self.backend.post_blocker(str(self.parent_number), f"LIVE-E2E blocker {marker}")
        self.assertTrue(blocker_ref)

        resolved = self.backend.resolve(slug)
        self.assertEqual(resolved["issueBody"], rewritten_body)
        self.assertEqual(resolved["Slug"], slug)
        self.assertEqual(resolved["Skipped States"], "UI")
        self.assertEqual(resolved["Status"], "Product")
        self.assertEqual(resolved["Gate State"], "Review Required")
        self.assertEqual(resolved["Lifecycle"], "Planning")
        comments = self.backend.comments(str(self.parent_number))
        self.assertTrue(any(comment["body"] == edited_body for comment in comments))
        self.assertFalse(any(comment["body"] == comment_body for comment in comments))

        page = self.backend.comments_page(str(self.parent_number), page=1, per_page=100)
        self.assertEqual(page.total, len(comments))
        self.assertEqual({comment["body"] for comment in page.comments}, {comment["body"] for comment in comments})

        # --- attached pull requests ---
        numbers = self.backend.attach_pr(str(self.parent_number), 999999)
        self.assertEqual(numbers, [999999])
        self.assertEqual(self.backend.attached_prs(str(self.parent_number)), [999999])

        # --- delivery tasks ---
        task_input: list[TaskInput] = [{
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

        retitled_input: list[TaskInput] = [{**task_input[0], "title": "[CORE] live task (renamed)"}]
        third = self.backend.upsert_tasks(str(self.parent_number), retitled_input, tasks)
        self.assertEqual(third[0]["action"], "retitled")

        by_number = self.backend.tasks_by_number([str(self.task_number)])
        self.assertEqual(by_number[0]["number"], self.task_number)
        self.assertEqual(self.backend.task_pr_numbers(str(self.parent_number)), [])

        # --- close / reopen ---
        self.backend.close_task(str(self.task_number))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            task = self.backend.tasks_by_number([str(self.task_number)])[0]
            if task["state"] == "CLOSED":
                break
            time.sleep(1)
        self.assertEqual(task["state"], "CLOSED")

        self.backend.reopen_task(str(self.task_number))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            task = self.backend.tasks_by_number([str(self.task_number)])[0]
            if task["state"] == "OPEN":
                break
            time.sleep(1)
        self.assertEqual(task["state"], "OPEN")

        # --- identity ---
        self.assertTrue(self.backend.current_actor())
        self.assertEqual(self.backend.ref_label(), self.repository.rsplit("/", 1)[-1])

        # --- queue ---
        queue = self.backend.queue_items()
        self.assertTrue(any(entry["content"]["number"] == self.parent_number for entry in queue))
